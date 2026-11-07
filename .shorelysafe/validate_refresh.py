"""Validate Avalon refresh provenance and actual data age before publication."""
import datetime as dt
import hashlib
import json
import math
import re
import urllib.request
from pathlib import Path

UTC = dt.timezone.utc

def stamp(value):
    return dt.datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(UTC)

def fresh(value, now, hours=6):
    value = stamp(value)
    assert -0.25 <= (now - value).total_seconds() / 3600 <= hours, f'Stale/future data timestamp: {value}'
    return value.isoformat().replace('+00:00', 'Z')

def read(root, name):
    raw = (root / name).read_bytes()
    assert raw and not raw.startswith(b'version https://git-lfs.github.com/spec/'), f'Missing real data: {name}'
    return json.loads(raw)

def latest_available_noaa_cycle():
    base = 'https://nomads.ncep.noaa.gov/pub/data/nccf/com/petss/prod/'
    def listing(url):
        with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Avalon-six-hour-refresh/1.0'}), timeout=60) as response:
            return response.read().decode()
    dates = sorted(set(re.findall(r'petss\.(\d{8})/', listing(base))), reverse=True)
    for day in dates[:4]:
        cycles = re.findall(r'petss\.t(00|06|12|18)z\.csv\.tar\.gz', listing(base + 'petss.' + day + '/'))
        if cycles:
            return dt.datetime.strptime(day + max(cycles), '%Y%m%d%H').replace(tzinfo=UTC)
    raise AssertionError('No published NOAA station CSV cycle available; refusing stale guidance')

def validate_source(root, app, now=None):
    root = Path(root)
    now = now or dt.datetime.now(UTC)
    facts = {'gauge_usgs': '01411355', 'parameter_code': '72279', 'gauge_noaa': '8535419', 'observation_datum': 'NAVD88'}
    if app == 'flooddashboard--avalon':
        meta, peaks, rows = [read(root, name) for name in ['data/petss_meta.json', 'data/peaks_navd88.json', 'data/petss_forecast.json']]
        assert meta['stid'] == '8535419' and meta['datum'] == 'MLLW'
        assert meta['forecast_product'] == 'TWL' and meta['forecast_statistic'] == 'ensemble_mean'
        assert peaks['site'] == '01411355' and peaks['parameterCd'] == '72279' and peaks['datum'] == 'NAVD88'
        cycle = dt.datetime.strptime(meta['run_dir'] + meta['cycle'], 'petss.%Y%m%dt%Hz').replace(tzinfo=UTC)
        facts.update(forecast_cycle_utc=fresh(cycle.isoformat(), now, 18), forecast_fetched_at_utc=fresh(meta['updated_utc'], now), latest_observation_utc=fresh(peaks['lastProcessedISO'], now), forecast_end_utc=max(stamp(row['t']) for row in rows).isoformat())
        assert stamp(facts['forecast_end_utc']) >= now + dt.timedelta(hours=24), 'Insufficient future NOAA coverage'
        assert peaks['events'] and all(math.isfinite(float(r['twl'])) for r in rows)
    elif app == 'floodmapper--avalon':
        forecast, observed, tops = [read(root, name) for name in ['forecast.json', 'observed.json', 'toptides.json']]
        assert forecast['stationId'] == '8535419' and forecast['usgsGaugeId'] == '01411355'
        assert forecast['operationalForecastProduct'] == 'TWL' and forecast['operationalForecastStatistic'] == 'ensemble_mean'
        assert forecast['navd88OffsetFromMllwFt'] == -2.58 and forecast['mapDatum'] == 'NAVD88'
        assert forecast['thresholdsNAVD88'] == {'minorLow': 3.42, 'moderateLow': 4.42, 'majorLow': 5.22}
        assert observed['site'] == '01411355' and observed['parameterCd'] == '72279' and observed['datum'] == 'NAVD88'
        assert observed['navd88OffsetFromMllwFt'] == -2.58
        latest = max(stamp(hour['timeUtc']) for day in observed['days'] for hour in day.get('hours', []) if hour.get('navd88StageFt') is not None)
        facts.update(forecast_cycle_utc=fresh(forecast['petssCycleUtc'], now, 18), forecast_fetched_at_utc=fresh(forecast['issuedUtc'], now), latest_observation_utc=fresh(latest.isoformat(), now), archive_refreshed_at_utc=fresh(observed['lastProcessedISO'], now), peaks_refreshed_at_utc=fresh(tops['generatedAt'], now), forecast_end_utc=forecast['forecastEndUtc'])
        assert stamp(forecast['forecastEndUtc']) >= now + dt.timedelta(hours=24)
        assert forecast['hours'] and tops['toptides']
    elif app == 'roads-at-risk--avalon':
        stats = read(root, 'flood_stats.json')
        assert stats['station']['usgsGaugeId'] == '01411355' and stats['station']['usgsParameterCode'] == '72279' and stats['station']['datum'] == 'NAVD88'
        assert stats['datum']['navd88OffsetFromMllwFt'] == -2.58
        assert stats['thresholds']['navd88'] == {'minor': 3.42, 'moderate': 4.42, 'major': 5.22}
        refresh = stats['observationRefresh']
        assert refresh['site'] == '01411355' and refresh['parameterCd'] == '72279' and refresh['datum'] == 'NAVD88'
        assert refresh['units'] == 'ft' and refresh['timeZone'] == 'America/New_York'
        facts.update(latest_observation_utc=fresh(refresh['latestObservationUtc'], now), archive_refreshed_at_utc=fresh(refresh['fetchedAtUtc'], now), archive_end_date=stats['archive']['endDate'], operational_weather_forecast=False)
        assert len(stats['dailyPeakArchive']) == stats['archive']['days'] == len(stats['dailyPeakNavd88Ft'])
    else:
        raise AssertionError('This refresh is scoped to the three existing Avalon apps')
    if 'forecast_cycle_utc' in facts:
        newest = latest_available_noaa_cycle()
        assert stamp(facts['forecast_cycle_utc']) == newest, 'A newer published NOAA cycle exists; refresh source data before publication'
        facts['newest_published_cycle_verified_utc'] = newest.isoformat().replace('+00:00', 'Z')
    return facts

def status(root, app, source_commit, facts, paths, published_files):
    import os
    source = {}
    for name in paths:
        p = Path(root) / name
        if p.is_file():
            source[name] = {'source_sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'published_sha256': published_files[name]['sha256'], 'bytes': published_files[name]['size']}
    repository = os.environ.get('GITHUB_REPOSITORY', '')
    return {'schema': 'shorelysafe-six-hour-refresh-v1', 'town': 'avalon', 'app_id': app, 'cadence_hours': 6, 'refreshed_at_utc': dt.datetime.now(UTC).isoformat().replace('+00:00', 'Z'), 'repository': repository, 'source_commit': source_commit, 'run_url': 'https://github.com/' + repository + '/actions/runs/' + os.environ.get('GITHUB_RUN_ID', ''), 'source': facts, 'payloads': source}
