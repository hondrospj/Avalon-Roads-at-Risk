const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');
const {derive,update,check,dayOf}=require('../tools/update_history');
const baseline=()=>JSON.parse(fs.readFileSync('flood_stats.json','utf8'));
test('current v2 history regenerates its exact existing aggregates and fixed science',()=>{
 const a=baseline(),b=derive(a,a.dailyPeakArchive);
 for(const key of ['archive','dailyPeakArchive','dailyPeakNavd88Ft','topEvents','tideModel','datum','thresholds','verticalUncertaintyFt'])assert.deepEqual(b[key],a[key],key);
});
test('new native Avalon daily maximum updates history while preserving datum/model/calibration',()=>{
 const a=baseline(),day=new Date(Date.parse(a.archive.endDate+'T00:00:00Z')+86400000).toISOString().slice(0,10),now=new Date(day+'T14:25:00Z'),b=update(a,[{t:day+'T14:00:00Z',ft:3.8}],now);
 assert.equal(b.archive.endDate,day);assert.equal(b.dailyPeakArchive.at(-1).peakNavd88Ft,3.8);
 assert.equal(b.dailyPeakArchive.at(-1).classification,'minor');
 for(const key of ['tideModel','datum','thresholds','verticalUncertaintyFt'])assert.deepEqual(a[key],b[key]);
 assert.equal(dayOf('2026-10-28T02:00:00Z'),'2026-10-27');
});
test('wrong station/datum and stale/empty upstream data fail instead of stamping old history fresh',()=>{
 let a=baseline();a.station.usgsGaugeId='01411360';assert.throws(()=>check(a));
 a=baseline();a.station.datum='MLLW';assert.throws(()=>check(a));
 a=baseline();assert.throws(()=>update(a,[],new Date()));
 assert.throws(()=>update(a,[{t:'2026-10-27T00:00:00Z',ft:2}],new Date('2026-10-28T14:25:00Z')));
});
