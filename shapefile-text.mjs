// shp-write 0.4.3 writes one byte per JavaScript character in DBF text fields.
// Supply UTF-8 byte strings and identify that encoding with a .cpg sidecar.
const encoder = new TextEncoder();
const DBF_TEXT_BYTES = 254;

export function dbfUtf8String(value, maxBytes=DBF_TEXT_BYTES){
  let text = '', used = 0;
  for(const character of value){
    const bytes = encoder.encode(character);
    if(used + bytes.length > maxBytes) break;
    text += String.fromCharCode(...bytes);
    used += bytes.length;
  }
  return text;
}

export function encodeDbfText(collection){
  return {...collection, features:collection.features.map(feature => ({...feature,
    properties:Object.fromEntries(Object.entries(feature.properties || {}).map(([key,value]) =>
      [key, typeof value === 'string' ? dbfUtf8String(value) : value]))
  }))};
}
