import { buildRoadNetwork } from './road-centerlines.mjs?v=topology-2';

// Named anchors can constrain the default to its own road instead of taking a
// detour. Towns with a cross-street route use the municipal network as-is.
export function selectDefaultRoadProfile(collection, {contains=null, network, defaultRoad}){
  const {anchors, names} = defaultRoad;
  if(names?.length){
    const features = collection.features.filter(feature => names.includes(feature.properties?.PRIMENAME));
    if(!features.length) return null;
    network = buildRoadNetwork({type:'FeatureCollection', features}, {contains});
  }
  const route = network.route(anchors, .25);
  if(!route || route.coordinates.length < 2 || route.lengthM <= 0) return null;
  if(contains && route.coordinates.some(point => !contains(point))) return null;
  return route;
}
