# WildfireEventBC
## Dataset Description
The overall structure of the dataset is similar to WildfireSpreadTS and TS-SatFire. For each wildfire event, a daily datacube is generated, maintaining consistent temporal (1 day) and spatial (500 m) resolution. Each datacube includes 20 variables describing vegetation status, meteorological conditions, human activity, topography, and active fire detection. This unified spatiotemporal resolution facilitates training and inference with various deep learning models, such as semantic segmentation networks, time-series forecasting models, or video processing models.

To balance data availability, temporal continuity, and quality, the dataset includes MODIS LAI products and daily 500 m surface reflectance from Bands 1, 2, and 7 (Terra and Aqua) to represent vegetation status. Meteorological conditions are derived from ERA5-Land and include daily 2 m air temperature, 10 m eastward and northward wind components, total precipitation, and surface latent heat flux. Snow coverage, a key variable in northern regions, is also included, as it affects surface moisture and delays fuel exposure in winter and spring, influencing ignition likelihood and early spread.

Topographic variables include slope, aspect, and hillshade, all derived from high-resolution SRTM DEM data. Additionally, distances to the nearest waterbody are computed from OpenStreetMap (OSM) to represent natural firebreaks. For human activity, the dataset incorporates MODIS land use products and computes distances to infrastructure (roads, transportation, and railways) using OSM data. These infrastructure maps indicate areas of potential anthropogenic ignition and barriers to fire spread.

Wildfire activity is captured using MODIS active fire products (MOD14A1 and MYD14A1), and wildfire event boundaries and durations are obtained from the GlobFire dataset. MODIS fire products offer global coverage, daily updates, and long time-series data, making them suitable for capturing fire occurrence and intensity. GlobFire aggregates fire pixels into fire events, providing spatiotemporal consistency for modeling.

It can be downloaded from Google Drive at 
