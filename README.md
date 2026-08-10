# Avalon Roads at Risk

Static GitHub Pages app for drawing road and cross-section profiles through the Avalon municipal DEM.

The interface follows the North Wildwood Roads at Risk reference: threshold presets, NAVD88/MLLW conversion, terrain and hillshade views, saved multi-line cross sections, flood-history and future-frequency charts, and CSV/Shapefile exports.

Municipal constants:

- Observations: USGS 01411355, Avalon
- PETSS / NOAA station: 8535419
- NAVD88 thresholds: 3.42 ft minor, 4.42 ft moderate, 5.22 ft major
- MLLW thresholds: 6 ft minor, 7 ft moderate, 7.8 ft major
- MLLW = NAVD88 + 2.58 ft

Terrain source: USGS 3DEP Bare Earth DEM Dynamic ImageServer, clipped to the Avalon Borough boundary at 6.2-foot adaptive resolution.
