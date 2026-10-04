## COP31 priorities
**Resilient Cities & Buildings** (helping flood-prone towns cope with climate extremes) and **Awareness Across All Areas** (showing communities their own flood risk in a form anyone can read).

## The problem
River towns flood again and again, and the people who decide what to do about it (town councils, village leaders, residents) rarely have a simple way to see **who floods first as the river rises**, or **which measures would keep the most people dry**. 

Nadi, Fiji shows the problem clearly. It floods almost every year: 26 major floods since 1991. In March 2026, families in Nawaka and Kerebula were flooded again and about 40–50 families from Nawajikuma settlement evacuated. The people living there still cannot see, street by street, what a bigger flood means for them or which options would help most.

## Our solution
**Waterline** is a flood planning tool for any river town, built entirely from free global data. **Nadi is our test city**: the first place we have prepared, and the one we validated.

You pick a place and raise the river on a gauge (0–6 m above normal). As the water rises, you see which homes, schools, clinics, substations and roads it reaches, how many people get water inside their homes, and which neighbourhoods are hit hardest. You can then test three measures that flood-prone towns already use, alone or together:
- **clearing the river channel** (dredging lowers every flood, but the benefit fades as silt returns),
- **raising homes** (targeted where a lift actually keeps the water out),
- **riverbank vegetation** (nature-based buffers that slow and store water, and cut the silt that makes dredging necessary),

and compare how many people each keeps dry. A summary page shows the whole scenario in charts, and one click turns it into a plain-language plan for a council or community meeting.

**Adding a new town** means drawing its map box, running the same open-data pipeline and adding a short settings file (local floor height, existing flood projects, agencies). The flood model, comparison and plan writer do not change.

## What we found in Nadi (model estimates)
- At a **2 m** rise floodwater reaches about **1,300 people** and gets inside the homes of about **1,030**; at **4 m** it reaches about **6,100**; at **6 m** about **14,700**. The biggest jump comes between 3 and 3.25 m (about 1,900 more people), when water spills onto the flat floodplain.
- **Riverside villages are reached first.** Namotomoto is the most affected named community (about 390 people reached at 2 m, 640 at 3 m), and parts of Nawaka are reached from just a 0.75 m rise. **Sabeto Primary School** is reached at 1.5 m, two town clinics at 3.75 m and **Nadi Fire Station** at 5.5 m.
- **The best measure depends on the size of the flood.** With medium settings at a 2 m rise, raising 100 well-chosen homes by 1 m keeps about **435 people** dry, more than clearing the channel (−0.25 m, about 130) or riverbank vegetation (−5%, about 80); all three together keep about 630 dry. But at **3.25 m**, the edge of the floodplain, lowering the river by 0.25 m keeps about **1,640** people dry, nearly three times as many as raising homes (about 610).
- **Order matters.** When measures are combined, raising homes after the river is lowered protects more people than raising them first, because every lift then goes to a home that is still flooding.
- **Check against reality:** our two most affected villages, Namotomoto and Nawaka, are both named in flood reports from April 2016 and March 2026.

## How we built it
- **Data (all free and global, so any town can be prepared):** FABDEM bare-earth elevation (buildings and trees removed), Overture building footprints, WorldPop population, OpenStreetMap rivers, facilities, roads and place names, Global Mangrove Watch.
- **Flood model (Python):** for every 30 m patch of ground we compute its height above the river or sea it drains to (HAND), raise the water in 0.25 m steps and flood only ground that water connected to the river can reach, so hollows behind banks stay dry. In Nadi, each of 13,509 buildings, 46 facilities and 1,921 road sections gets the river rise at which water first reaches it.
- **Backend (FastAPI):** applies the measures, ranks the most affected areas and compares options; the plan is written by an LLM (Gemini) from the model's numbers only, with a built-in fallback.
- **Frontend (React, MapLibre):** a home page to choose a place, the map with the river gauge, and a summary page with charts and the written plan.
- **Checks:** known-answer tests for the flood model and backend, two elevation datasets compared, and Nadi's town centre and hotspots checked against past floods.

## Impact
- **For town councils and village leaders:** see where to act first (which homes to raise, which school or clinic needs a flood plan) using numbers they can question.
- **For communities:** an easy way to understand their own risk before the wet season.
- **For other flood-prone towns:** the same tool works anywhere the free global datasets cover. Fiji towns such as Ba, Rakiraki and Labasa would be next, and the pipeline is not tied to Fiji.
- **Honest by design:** every number is labelled as an estimate, measures are what-ifs with sources, and mangroves are shown for coastal protection but not counted as lowering river floods.

## Limits
A planning screen, not a flow simulation: 30 m elevation can be off by a metre or more, people are WorldPop estimates (in Nadi, about half of the area's residents fall in mapped buildings), floor heights are assumed (0.3 m in Nadi) and OpenStreetMap has gaps. Next steps: prepare a second town, co-design with communities and local agencies, surveyed floor heights and comparison with official flood maps.

**Tools, data licences and AI use** (Claude for planning and data scripts; Gemini for plan text) are listed in the README.