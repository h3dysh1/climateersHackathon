SAMPLE DATA (synthetic) for building the frontend before P2's real Nadi data is ready.

Made by running data-prep/hand_flood.py on an invented river valley near Nadi's coordinates.
Place names (Riverside, Upper Valley, Hilltop...) and facilities are made up.
The files have exactly the same format as the real ones, so when P2 delivers, just replace
these files: no code changes needed. Delete this README then.

buildings.json         [{id, lon, lat, ground_m, floods_at_m, people, type, area}]  -> send to backend
facilities.json        [{id, name, type, lon, lat, ground_m, floods_at_m}]          -> send to backend + map icons
roads.json             [{id, name, low_point_m, length_m}]                          -> send to backend
roads.geojson          LineStrings, properties {id, name, low_point_m}              -> map (colour cut roads)
flood_extents.geojson  Polygons, properties {level_m} every 0.5 m, 0.5..6.0         -> map water layer
hand_summary.json      settings and counts                                          -> info only
Heights are metres above normal river level (HAND). floods_at_m = 99 means never reached up to 6 m.
