"use strict";
const fs = require('node:fs');
const assert = require('node:assert/strict');
const {fetchObservations} = require('./usgs-observations');
const DAY = 86400000;
const dayFormatter = new Intl.DateTimeFormat('en-CA', {timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit'});
function dayOf(time){ const p=Object.fromEntries(dayFormatter.formatToParts(new Date(time)).map(x=>[x.type,x.value]));return `${p.year}-${p.month}-${p.day}`; }
function check(stats){
 assert.equal(stats.schema,'roads-at-risk-flood-stats-v2');
 assert.equal(stats.station.usgsGaugeId,'01411355');assert.equal(stats.station.usgsParameterCode,'72279');assert.equal(stats.station.datum,'NAVD88');
 assert.deepEqual(stats.datum,{navd88OffsetFromMllwFt:-2.58,mllwOffsetFromNavd88Ft:2.58});
 assert.deepEqual(stats.thresholds.navd88,{minor:3.42,moderate:4.42,major:5.22});
 assert.deepEqual(stats.thresholds.mllw,{minor:6,moderate:7,major:7.8});
}
function classify(value,thresholds){for(const key of ['major','moderate','minor'])if(value>=thresholds[key])return key;return'none';}
function derive(stats,rows){
 const out=structuredClone(stats),counts={none:0,minor:0,moderate:0,major:0};
 rows=rows.slice().sort((a,b)=>a.date.localeCompare(b.date));
 for(const row of rows)counts[row.classification]++;
 out.dailyPeakArchive=rows;
 out.dailyPeakNavd88Ft=rows.map(r=>r.peakNavd88Ft).sort((a,b)=>a-b);
 out.archive={...stats.archive,startDate:rows[0].date,endDate:rows.at(-1).date,days:rows.length,years:Math.round(rows.length/365.2425*100)/100,classificationCounts:counts};
 out.topEvents=rows.slice().sort((a,b)=>b.peakNavd88Ft-a.peakNavd88Ft||a.date.localeCompare(b.date)).slice(0,stats.topEvents.length).map((r,i)=>({rank:i+1,date:r.date,displayDate:new Date(r.date+'T12:00:00Z').toLocaleDateString('en-US',{timeZone:'UTC',month:'short',day:'numeric',year:'numeric'}),heightNavd88Ft:r.peakNavd88Ft,heightMllwFt:r.peakMllwFt,classification:r.classification}));
 return out;
}
function update(stats,observations,now=new Date()){
 check(stats);assert(observations.length,'No new source observations; archive not refreshed');
 const latest=observations.reduce((latest,row)=>Math.max(latest,Date.parse(row.t)),-Infinity);
 assert(Number.isFinite(latest)&&latest<=now.getTime()+900000&&now-latest<=6*3600000,'Upstream USGS observations are stale/future');
 const existing=new Map(stats.dailyPeakArchive.map(r=>[r.date,{...r}]));
 const minimum=new Date(Date.parse(stats.archive.endDate+'T00:00:00Z')-2*DAY).toISOString().slice(0,10);
 for(const row of observations){
  assert(Number.isFinite(row.ft),'Nonfinite observation');const date=dayOf(row.t);if(date<minimum)continue;
  const peak=Math.round((row.ft+1e-9)*100)/100,old=existing.get(date);
  // Retain stored complete-day maxima/official historical crests on overlap.
  if(!old||peak>old.peakNavd88Ft)existing.set(date,{date,peakNavd88Ft:peak,peakMllwFt:Math.round((peak+2.58)*100)/100,classification:classify(peak,stats.thresholds.navd88)});
 }
 const out=derive(stats,[...existing.values()]);
 out.generatedAt=now.toISOString();
 out.observationRefresh={site:'01411355',parameterCd:'72279',datum:'NAVD88',units:'ft',timeZone:'America/New_York',fetchedAtUtc:now.toISOString(),latestObservationUtc:new Date(latest).toISOString(),source:'USGS continuous API; WaterServices fallback',sourceUrl:'https://api.waterdata.usgs.gov/ogcapi/v1/collections/continuous/items?monitoring_location_id=USGS-01411355&parameter_code=72279',method:'Local-calendar daily maxima; stored maxima retained on overlap; existing tide/trend calibration unchanged',observationsFetched:observations.length};
 assert.deepEqual(out.tideModel,stats.tideModel);assert.deepEqual(out.thresholds,stats.thresholds);assert.deepEqual(out.datum,stats.datum);assert.equal(out.verticalUncertaintyFt,stats.verticalUncertaintyFt);
 return out;
}
async function main(){
 const path='flood_stats.json',stats=JSON.parse(fs.readFileSync(path,'utf8'));check(stats);
 const now=new Date(),startISO=new Date(Date.parse(stats.archive.endDate+'T00:00:00Z')-3*DAY).toISOString();
 const rows=await fetchObservations({site:'01411355',parameter:'72279',startISO,endISO:now.toISOString()});
 const out=update(stats,rows,now);fs.writeFileSync(path+'.tmp',JSON.stringify(out,null,2)+'\n');fs.renameSync(path+'.tmp',path);
 console.log(JSON.stringify({archive:out.archive,source:out.observationRefresh,preservedTideAndTrend:true}));
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports={dayOf,check,classify,derive,update};
