## COP31 priorities
**Resilient Cities & Buildings** (helping a town cope with climate extremes) and **Awareness Across All Areas** (showing communities their own flood risk in a form anyone can read).

## The problem
Nadi, Fiji floods almost every year: 26 major floods since 1991. The January 2009 flood killed 11 people, left 12,000 homeless and caused FJD 113 million in damage. In March 2026, families in Nawaka and Kerebula were flooded again and about 40–50 families from Nawajikuma settlement evacuated. Australia and the ADB are funding the Nadi Flood Alleviation Project, but councils, village leaders and residents still have no simple way to see **who floods first as the river rises**, or **which measures would keep the most people dry** before the next wet season.

## Our solution
**Nadi Flood Planner** is a map with one slider: how far the Nadi River rises above normal (0–6 m). As you raise it, you see which homes, schools, clinics, substations and roads floodwater reaches, how many people are affected and which areas are hit hardest. You can then test three measures, alone or together:
- **clearing the river channel** (dredging lowers every flood),
- **raising homes** (targeted where a lift actually keeps water out),
- **riverbank vegetation** (nature-based buffers that slow and store water),

and compare how many people each keeps dry. One click turns the result into a plain-language plan for a council or community meeting.

## What we found (Nadi, model estimates)
- At a **2 m** rise floodwater reaches about **1,700 people**; at **4 m** about **6,300**; at **6 m** about **14,700**. The numbers jump sharply above about 3 m, when water spreads across the flat floodplain.
- The first places reached are **riverside villages**: Namotomoto and Nawaka are the most affected named communities at 2 m. **Sabeto Primary School** is reached at 1.5 m, two town clinics at 3.75 m and **Nadi Fire Station** at 5.5 m.
- With the app's medium settings, **raising 100 well-chosen homes by 1 m keeps about 390 people dry** at a 2 m rise, more than dredging (−0.25 m, about 120) or riverbank vegetation (−5%, about 80). All three together keep about 570 people dry.
- **Check against reality:** the villages our model ranks highest are the ones named in flood reports from April 2016 and March 2026.

## How we built it
- **Data (all free and global):** FABDEM bare-earth elevation (buildings and trees removed), Overture building footprints, WorldPop 2020 population, OpenStreetMap rivers, facilities, roads and place names, Global Mangrove Watch.
- **Flood model (Python):** for every 30 m patch of ground we compute its height above the river or sea it drains to (HAND), raise the water in 0.25 m steps and flood only ground that water connected to the river can reach, so hollows behind banks stay dry. Each of 13,509 buildings, 51 facilities and 1,933 road sections gets the river rise at which water first reaches it.
- **Backend (FastAPI):** applies the measures, ranks the most affected areas and compares options; the plan is written by an LLM (Gemini) with a built-in fallback.
- **Frontend (React, MapLibre, deck.gl):** the interactive map and slider.
- **Checks:** known-answer tests for the flood model, two elevation datasets compared, and the town centre checked against past floods.

## Impact
- **For Nadi Town Council and village leaders:** see where to act first (which homes to raise, which school or clinic needs a flood plan) using numbers they can question.
- **For communities:** an easy way to understand their own risk before the wet season (November–April).
- **Reusable:** change the map box and re-run the open-data pipeline to use it for another river town (Ba, Rakiraki, Labasa).
- **Honest by design:** every number is labelled as an estimate, measures are what-ifs with sources, and mangroves are shown for coastal protection but not counted as lowering river floods.

## Limits
A planning screen, not a flow simulation: 30 m elevation can be off by a metre or more, people are WorldPop estimates (about half of the area's residents fall in mapped buildings), floor heights are assumed (0.3 m) and OpenStreetMap has gaps. Next steps: co-design with communities and Fiji agencies, surveyed floor heights and comparison with official flood maps.

**Tools, data licences and AI use** (Claude for planning and data scripts; Gemini for plan text) are listed in the README.
