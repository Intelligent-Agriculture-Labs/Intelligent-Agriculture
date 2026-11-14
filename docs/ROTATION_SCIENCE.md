# Rotation science: the biology behind FieldShift's rotation planner

FieldShift's rotation advice uses three data files:

| File | What it holds |
|---|---|
| `backend/fieldshift/config/crops_extra.yaml` | 34 more crops (52 in total with `crops.yaml`), using the same water and yield schema as the season model. Each crop has a `sources:` list. |
| `backend/fieldshift/config/rotation_knowledge.yaml` | 30 soil- and residue-borne organisms, one rotation profile for every crop, and 22 general rules. |
| This document | The principles behind those numbers, and the references. |

Every number in these files comes from a named source. If a source gives a range, we use its midpoint and say so in the entry's note. If a value comes from expert judgement or a qualitative source, the entry carries `low_confidence: true`.

## 1. Why rotation works: the "rotation effect"

A crop grown after a different crop usually yields more than the same crop grown after itself, even when both get full fertiliser. Long-term trials show:

- **Wheat.** Across more than 900 comparisons, wheat after a break crop yielded 0.5 t/ha more (after oats) to 1.2 t/ha more (after grain legumes) than wheat after wheat. The ranking of break crops was oats < canola ≈ mustard ≈ flax < pea ≈ faba bean ≈ chickpea ≈ lentil. About 20 % (after canola) to 60 % (after legumes) of the benefit carries over into a second wheat crop (Angus et al. 2015; Kirkegaard et al. 2008).
- **Maize.** Continuous maize yielded 1.36 t/ha (13 %) less than maize after soybean in Illinois, and the penalty grew for up to seven years (Gentry et al. 2013). In Wisconsin, rotated maize yielded 15 % more and first-year soybean 8 % more (Pedersen & Lauer 2003).
- **Diversity and drought.** In 11 long-term North American experiments, more diverse rotations raised maize yields by 28 % on average and cut yield losses in drought years by 14–90 % (Bowles et al. 2020).

Bennett et al. (2012) traced this "yield decline in short rotations" to four mechanisms. The data files model each one.

### 1.1 Specialised soil and residue organisms (the largest effect)

Most root diseases and nematodes attack only one plant family. Without a host they slowly die out. Two numbers describe each organism:

- `survival_years`: how long it persists without a host.
- `break_years`: how many host-free years are recommended.

The two numbers can be far apart, and the gap decides the advice:

| Organism | Persistence | Rotation consequence |
|---|---|---|
| Take-all (*Gaeumannomyces*) | About 1 year on stubble | One non-grass year controls it. Oats are immune. Continuous wheat can develop "take-all decline" (Cook 2003). |
| Corn rootworm | Larvae feed only on maize roots | One year without maize breaks the cycle, unless rotation-resistant variants are present (Gray et al. 2009). |
| *Sclerotinia* sclerotia | About 5 years, with more than 400 broadleaf hosts | Never grow two hosts in a row: sunflower, canola, soybean, beans, pulses, carrot and potato are all hosts (Bolton et al. 2006). |
| Clubroot spores | 15–20 years | Most spores die within two brassica-free years, so the minimum is two years. Oilseed rape, mustard covers and cabbage all count as brassica years (Dixon 2009; Wallenhammar 1996; Canola Council). |
| Potato cyst nematode | 20+ years | Eggs decline only about 20–33 % per year, so infested fields need at least 6 years between potato crops (Whitehead 1995). |
| *Aphanomyces* in peas and lentils | 10+ years | The reason for 5–8-year pea breaks (Gaulin et al. 2007). |
| Onion white rot | 20+ years | Rotation alone cannot clean a field (UC IPM). |
| *Striga* seed | 10–20 years | Counters are legume "trap crops" (cowpea, groundnut, soybean, pigeon pea), which make Striga seed germinate with no cereal host, plus N fertility (Oswald 2005; Parker 2009). |
| Fall armyworm | None in the soil (migratory) | Rotation does not help. It is included so the app does not suggest that it does (Day et al. 2017). |

The planner follows three practical rules:

1. **Host groups decide spacing.** Spacing is checked across every host of the same organism, not only repeats of the same crop. Sugar beet after oilseed rape counts as a "beet year" for beet cyst nematode, because brassicas and chenopods also host it.
2. **Long-surviving organisms are not "fixed" by rotation.** These include *Verticillium* (about 14 years), *Pythium* and rhizomania. For them the advice is to avoid making things worse, not to expect a cure.
3. **Some crops build populations without being damaged.** Grass and leys build up wireworms (`favoured_by`). The damage falls 2–4 years later on potatoes, maize and root crops (Parker & Howard 2001).

### 1.2 Nitrogen: biological fixation and immobilisation

Legumes fix atmospheric N₂. The N credit to the next crop, `n_effect_kg_ha`, comes from Peoples et al. (2009) and Herridge et al. (2008):

| Predecessor | N credit to next crop |
|---|---|
| Alfalfa | +120 kg/ha |
| Grass–clover ley | +100 kg/ha |
| Faba bean | +45 kg/ha |
| Pea, cowpea, pigeon pea | +40 kg/ha |
| Soybean | +20 kg/ha (most of its N leaves with the high-protein grain) |

Some crops lock up N instead. Residues with a high carbon-to-nitrogen ratio (maize stover, sorghum, cereal straw, cane trash) hold soil N while they decompose, so their values are negative.

Oilseed rape and beet leaves leave mineral N behind (+30 kg/ha). Catch crops such as mustard, phacelia and cereal rye hold N that would otherwise leach. In a meta-analysis, non-legume covers caused no significant yield penalty (Tonitto et al. 2006).

### 1.3 Soil structure, roots and water

Taproots (oilseed rape, safflower, alfalfa, pigeon pea, hemp, sugar beet) leave channels that later roots follow. Perennial leys rebuild aggregates and organic matter, and grass–clover mixtures yield more N than clover alone (Nyfeler et al. 2011). These crops get `soil_structure_effect: improves`.

Several crops get `degrades`:

- Potato and sugar beet: intensive tillage and wet harvest traffic.
- Silage maize: almost no residue returned.
- Cassava: slow early canopy, high erosion.
- Groundnut: digging at harvest leaves the soil bare.
- Puddled rice: puddling destroys structure for the next upland crop (Timsina & Connor 2001).

Deep-rooted crops such as sunflower and safflower also dry out the subsoil, so the next crop starts with less stored water. This trade-off matters most in semi-arid regions.

### 1.4 Plant–soil chemistry: allelopathy and mycorrhiza

- **Allelopathy.** Sorghum (sorgoleone), sunflower (phenolics) and cereal rye (benzoxazinoids) release compounds that suppress weeds. The same compounds can reduce emergence of small-seeded crops sown soon after (Weston 1996; Weston & Duke 2003). Alfalfa poisons its own seedlings, so a new stand needs at least one year with another crop first (Jennings & Nelson 1998).
- **Biofumigation.** Brassica glucosinolates break down into isothiocyanates that suppress some soil pathogens and nematodes (Kirkegaard & Sarwar 1998; Matthiessen & Kirkegaard 2006). Brassicas still host clubroot and beet cyst nematode, so they count as host years.
- **Mycorrhiza.** Brassicas, sugar beet and quinoa do not form arbuscular mycorrhiza, and long bare fallows lose mycorrhizal propagules. Strongly mycorrhizal crops (sunflower, flax, maize, chickpea, pigeon pea, cotton) then become phosphorus-deficient. In one experiment, re-inoculating the soil more than doubled sunflower growth (Thompson 1987, "long fallow disorder").

## 2. How the files turn this into advice

- **Same-crop spacing.** `crops.<id>.min_return_years` is the lower bound of the published range, and the note gives the full range. The main source is the Landwirtschaftskammer NRW break table (after Kolbe et al.): wheat 2, oats 3–5, flax 6, sunflower 6, sugar beet 4, rapeseed 3–5, pea 4–8, lentil 5, clover-grass 3–4 years. These are cross-checked against AHDB, the Canola Council and the review literature.
- **Family spacing.** `family_return_years` catches pairs such as tomato and potato (shared PCN and *Verticillium*) or pea and lentil (shared *Aphanomyces*).
- **Predecessor value.** `preceding_crop_value` comes from the German *Vorfruchtwert* concept. The Saxon State Office (LfULG) table puts the next crop's yield at 110–120 % after a very favourable predecessor, down to 80–90 % after a very unfavourable one. Rule `predecessor_value_scale` uses the class midpoints: high = +15 %, medium = +5 %, low = −5 %.
- **Rules.** `rules` (22 entries) state each effect as a percentage on the affected crop (`applies_to`) after given predecessors (`after`), within a time window (`window_years`) or for a pathogen host group (`host_group`). Effect sizes taken from quantitative sources carry no flag, for example:
  - cereal after cereal: −10 %
  - legume before cereal: +20 %
  - oilseed before cereal: +15 %
  - continuous maize: −13 %
  - soybean after soybean: −8 %
  - brassicas closer than one in three years: −11 % per missing break year (Harker et al. 2015)
  - more diverse maize rotations: +28 %

  Effects taken from qualitative sources are marked `low_confidence`.
- **Crop parameters.** The water and yield values in `crops_extra.yaml` follow the season model's conventions:
  - Kc values, stage lengths, rooting depth and depletion fraction p: FAO-56 Tables 11, 12 and 22, with the table row cited per crop.
  - Yield response factor Ky: FAO-33 seasonal values, as reproduced in FAO-66 Table 1.
  - Water productivity WP\* and harvest index HI: AquaCrop where available.
  - Crops not covered by FAO-56 (rye, spelt, winter rape stage lengths, chickpea stage lengths, pigeon pea, buckwheat, quinoa, hemp, phacelia, grass–clover ley) are marked `low_confidence`. Prices and costs are indicative 2023–24 values, and the farmer should edit them.

## 3. Limits

- Break lengths are general guidance. Local inoculum, pathotypes, resistant varieties, tillage and climate can shorten or lengthen them. Soil tests (for PCN, *Aphanomyces*, SCN or clubroot) override the defaults.
- Yield effects come from specific regions and should not be added up blindly. The checker should cap the combined effect.
- Pathogen host lists are simplified to the crops in FieldShift. Weeds and volunteers can keep pathogens alive between hosts.

## References

- Ae N. et al. 1990. Phosphorus uptake by pigeon pea and its role in cropping systems of the Indian subcontinent. *Science* 248:477–480. https://doi.org/10.1126/science.248.4954.477
- AHDB. Non-chemical control of take-all in cereals; Rotation, cultivation and drilling options for cereal disease management; Eyespot in cereals and risk assessment in wheat. https://ahdb.org.uk/knowledge-library/
- Ajayi-Oyetunde O.O., Bradley C.A. 2018. *Rhizoctonia solani*: taxonomy, population biology and management of rhizoctonia seedling disease of soybean. *Plant Pathology* 67:3–17. https://doi.org/10.1111/ppa.12733
- Allen R.G., Pereira L.S., Raes D., Smith M. 1998. Crop evapotranspiration. FAO Irrigation and Drainage Paper 56. https://www.fao.org/3/x0490e/x0490e00.htm
- Amaducci S. et al. 2015. Key cultivation techniques for hemp in Europe and China. *Industrial Crops and Products* 68:2–16. https://doi.org/10.1016/j.indcrop.2014.06.041
- Angus J.F. et al. 2015. Break crops and rotations for wheat. *Crop & Pasture Science* 66:523–552. https://doi.org/10.1071/CP14252
- Bennett A.J. et al. 2012. Meeting the demand for crop production: the challenge of yield decline in crops grown in short rotations. *Biological Reviews* 87:52–71. https://doi.org/10.1111/j.1469-185X.2011.00184.x
- Bolton M.D., Thomma B.P.H.J., Nelson B.D. 2006. *Sclerotinia sclerotiorum* (Lib.) de Bary: biology and molecular traits of a cosmopolitan pathogen. *Molecular Plant Pathology* 7:1–16. https://doi.org/10.1111/j.1364-3703.2005.00316.x
- Bowles T.M. et al. 2020. Long-term evidence shows that crop-rotation diversification increases agricultural resilience to adverse growing conditions in North America. *One Earth* 2:284–293. https://doi.org/10.1016/j.oneear.2020.02.007
- Canola Council of Canada. Canola Encyclopedia: Clubroot; Blackleg. https://www.canolacouncil.org/canola-encyclopedia/diseases/
- Clark A. (ed.) 2007. *Managing Cover Crops Profitably*, 3rd ed. SARE. https://www.sare.org/resources/managing-cover-crops-profitably-3rd-edition/
- Cook R.J. 2003. Take-all of wheat. *Physiological and Molecular Plant Pathology* 62:73–86. https://doi.org/10.1016/S0885-5765(03)00042-0
- Day R. et al. 2017. Fall armyworm: impacts and implications for Africa. *Outlooks on Pest Management* 28:196–201. https://doi.org/10.1564/v28_oct_02
- Dees M.W., Wanner L.A. 2012. In search of better management of potato common scab. *Potato Research* 55:249–268. https://doi.org/10.1007/s11540-012-9206-9
- Dill-Macky R., Jones R.K. 2000. The effect of previous crop residues and tillage on Fusarium head blight of wheat. *Plant Disease* 84:71–76. https://doi.org/10.1094/PDIS.2000.84.1.71
- Dixon G.R. 2009. The occurrence and economic impact of *Plasmodiophora brassicae* and clubroot disease. *J. Plant Growth Regulation* 28:194–202. https://doi.org/10.1007/s00344-009-9090-y
- Dorrance A.E. et al. 2007. Phytophthora root and stem rot of soybean. *The Plant Health Instructor*. https://doi.org/10.1094/PHI-I-2007-0830-07
- FAO 2013. Save and Grow: Cassava. https://www.fao.org/3/i3278e/i3278e.pdf
- Fitt B.D.L., Goulds A., Polley R.W. 1988. Eyespot epidemiology in relation to prediction of disease severity and yield loss in winter wheat: a review. *Plant Pathology* 37:311–328. https://doi.org/10.1111/j.1365-3059.1988.tb02081.x
- Fradin E.F., Thomma B.P.H.J. 2006. Physiology and molecular aspects of Verticillium wilt diseases caused by *V. dahliae* and *V. albo-atrum*. *Molecular Plant Pathology* 7:71–86. https://doi.org/10.1111/j.1364-3703.2006.00323.x
- Garcia M., Raes D., Jacobsen S.-E. 2003. Evapotranspiration analysis and irrigation requirements of quinoa in the Bolivian highlands. *Agric. Water Manage.* 60:119–134. https://doi.org/10.1016/S0378-3774(02)00162-2
- Gaulin E. et al. 2007. Root rot disease of legumes caused by *Aphanomyces euteiches*. *Molecular Plant Pathology* 8:539–548. https://doi.org/10.1111/j.1364-3703.2007.00413.x
- Geerts S. et al. 2009. Simulating yield response of quinoa to water availability with AquaCrop. *Agron. J.* 101:499–508. https://doi.org/10.2134/agronj2008.0137s
- Gentry L.F., Ruffo M.L., Below F.E. 2013. Identifying factors controlling the continuous corn yield penalty. *Agron. J.* 105:295–303. https://doi.org/10.2134/agronj2012.0246
- Gray M.E. et al. 2009. Adaptation and invasiveness of western corn rootworm. *Annu. Rev. Entomol.* 54:303–321. https://doi.org/10.1146/annurev.ento.54.110807.090434
- Harker K.N. et al. 2015. Canola rotation frequency impacts canola yield and associated pest species. *Can. J. Plant Sci.* 95:9–20. https://doi.org/10.4141/cjps-2014-289
- Hausbeck M.K., Lamour K.H. 2004. *Phytophthora capsici* on vegetable crops. *Plant Disease* 88:1292–1303. https://doi.org/10.1094/PDIS.2004.88.12.1292
- Herridge D.F., Peoples M.B., Boddey R.M. 2008. Global inputs of biological nitrogen fixation in agricultural systems. *Plant and Soil* 311:1–18. https://doi.org/10.1007/s11104-008-9668-3
- Hof-Kautz C. 2024. Fruchtfolgen im Ökolandbau (Anbaupausen). Landwirtschaftskammer NRW. https://www.oekolandbau.nrw.de/sites/default/files/2024-06/2024_2_DLG_Poster_Fruchtfolgen_im_Ökolandbau.pdf
- Jacobsen S.-E. 2003. The worldwide potential for quinoa. *Food Reviews International* 19:167–177. https://doi.org/10.1081/FRI-120018883
- Jennings J.A., Nelson C.J. 1998. Influence of soil texture on alfalfa autotoxicity. *Agron. J.* 90:54–58. https://doi.org/10.2134/agronj1998.00021962009000010010x
- Jensen E.S., Peoples M.B., Hauggaard-Nielsen H. 2010. Faba bean in cropping systems. *Field Crops Research* 115:203–216. https://doi.org/10.1016/j.fcr.2009.10.008
- Kfir R. et al. 2002. Biology and management of economically important lepidopteran cereal stem borers in Africa. *Annu. Rev. Entomol.* 47:701–731. https://doi.org/10.1146/annurev.ento.47.091201.145254
- Kirkegaard J. et al. 2008. Break crop benefits in temperate wheat production. *Field Crops Research* 107:185–195. https://doi.org/10.1016/j.fcr.2008.02.010
- Kirkegaard J.A., Sarwar M. 1998. Biofumigation potential of brassicas I. *Plant and Soil* 201:71–89. https://doi.org/10.1023/A:1004364713152
- Larkin R.P. et al. 2011. Effects of different potato cropping system approaches and water management on soilborne diseases and soil microbial communities. *Phytopathology* 101:58–67. https://doi.org/10.1094/PHYTO-04-10-0100
- LfULG Sachsen. Vorfruchteignung der Kulturarten im Ökologischen Landbau (Fruchtfolgegrundsätze). https://www.landwirtschaft.sachsen.de/download/Fruchtfolgegrundsaetze_Tabelle.pdf
- Luo Q. 2011. Temperature thresholds and crop production: a review. *Climatic Change* 109:583–598. https://doi.org/10.1007/s10584-011-0028-6
- Lutman P.J.W. et al. 2013. A review of the effects of crop agronomy on the management of *Alopecurus myosuroides*. *Weed Research* 53:299–313. https://doi.org/10.1111/wre.12024
- Matthiessen J.N., Kirkegaard J.A. 2006. Biofumigation and enhanced biodegradation. *Crit. Rev. Plant Sci.* 25:235–265. https://doi.org/10.1080/07352680600611543
- McGrann G.R.D. et al. 2009. Progress towards the understanding and control of sugar beet rhizomania disease. *Molecular Plant Pathology* 10:129–141. https://doi.org/10.1111/j.1364-3703.2008.00514.x
- McMullen M. et al. 2012. A unified effort to fight an enemy of wheat and barley: Fusarium head blight. *Plant Disease* 96:1712–1728. https://doi.org/10.1094/PDIS-03-12-0291-FE
- Moens M., Perry R.N., Starr J.L. 2009. *Meloidogyne* species: a diverse group of novel and important plant parasites. In *Root-knot Nematodes*, CABI. https://doi.org/10.1079/9781845934927.0001
- Niblack T.L. 2005. Soybean cyst nematode management reconsidered. *Plant Disease* 89:1020–1026. https://doi.org/10.1094/PD-89-1020
- Nyfeler D. et al. 2011. Grass–legume mixtures can yield more nitrogen than legume pure stands. *Agric. Ecosyst. Environ.* 140:155–163. https://doi.org/10.1016/j.agee.2010.11.022
- Oswald A. 2005. Striga control: technologies and their dissemination. *Crop Protection* 24:333–342. https://doi.org/10.1016/j.cropro.2004.09.003
- Parker C. 2009. Observations on the current status of *Orobanche* and *Striga* problems worldwide. *Pest Manag. Sci.* 65:453–459. https://doi.org/10.1002/ps.1713
- Parker W.E., Howard J.J. 2001. The biology and management of wireworms (*Agriotes* spp.) on potato. *Agric. For. Entomol.* 3:85–98. https://doi.org/10.1046/j.1461-9563.2001.00094.x
- Pedersen P., Lauer J.G. 2003. Corn and soybean response to rotation sequence, row spacing, and tillage system. *Agron. J.* 95:965–971. https://doi.org/10.2134/agronj2003.9650
- Peoples M.B. et al. 2009. The contributions of nitrogen-fixing crop legumes to the productivity of agricultural systems. *Symbiosis* 48:1–17. https://doi.org/10.1007/BF03179980
- Porter J.R., Gawith M. 1999. Temperatures and the growth and development of wheat: a review. *Eur. J. Agron.* 10:23–36. https://doi.org/10.1016/S1161-0301(98)00047-1
- Prasanna B.M. et al. (eds) 2018. *Fall Armyworm in Africa: A Guide for Integrated Pest Management*. CIMMYT. https://repository.cimmyt.org/handle/10883/19204
- Raes D. et al. 2009 / Steduto P. et al. 2009. AquaCrop: the FAO crop model, parts I and II. *Agron. J.* 101:426–447. https://doi.org/10.2134/agronj2008.0139s
- Sánchez B., Rasmussen A., Porter J.R. 2014. Temperatures and the growth and development of maize and rice: a review. *Global Change Biology* 20:408–417. https://doi.org/10.1111/gcb.12389
- Smiley R.W. et al. 2017. Cereal cyst nematodes: a complex and destructive group of *Heterodera* species. *Plant Disease* 101:1692–1720. https://doi.org/10.1094/PDIS-03-17-0355-FE
- Steduto P., Hsiao T.C., Fereres E., Raes D. 2012. Crop yield response to water. FAO Irrigation and Drainage Paper 66. https://www.fao.org/3/i2800e/i2800e.pdf
- Thompson J.P. 1987. Decline of vesicular-arbuscular mycorrhizae in long fallow disorder of field crops. *Aust. J. Agric. Res.* 38:847–867. https://doi.org/10.1071/AR9870847
- Thompson J.P. et al. 2008. Root-lesion nematodes (*Pratylenchus thornei* and *P. neglectus*): a review. *Australasian Plant Pathology* 37:235–242. https://doi.org/10.1071/AP08021
- Timsina J., Connor D.J. 2001. Productivity and management of rice–wheat cropping systems. *Field Crops Research* 69:93–132. https://doi.org/10.1016/S0378-4290(00)00143-X
- Tivoli B., Banniza S. 2007. Comparison of the epidemiology of ascochyta blights on grain legumes. *Eur. J. Plant Pathol.* 119:59–76. https://doi.org/10.1007/s10658-007-9117-9
- Tonitto C., David M.B., Drinkwater L.E. 2006. Replacing bare fallows with cover crops in fertilizer-intensive cropping systems: a meta-analysis. *Agric. Ecosyst. Environ.* 112:58–72. https://doi.org/10.1016/j.agee.2005.07.003
- UC IPM. Sugarbeet cyst nematode; Onion and garlic white rot. https://ipm.ucanr.edu/
- van West P., Appiah A.A., Gow N.A.R. 2003. Advances in research on oomycete root pathogens. *Physiol. Mol. Plant Pathol.* 62:99–113. https://doi.org/10.1016/S0885-5765(03)00044-4
- Wallenhammar A.-C. 1996. Prevalence of *Plasmodiophora brassicae* in a spring oilseed rape growing area in central Sweden. *Plant Pathology* 45:710–719. https://doi.org/10.1046/j.1365-3059.1996.d01-173.x
- Ward J.M.J. et al. 1999. Gray leaf spot: a disease of global importance in maize production. *Plant Disease* 83:884–895. https://doi.org/10.1094/PDIS.1999.83.10.884
- West J.S. et al. 2001. Epidemiology and management of *Leptosphaeria maculans* (phoma stem canker) on oilseed rape in Australia, Canada and Europe. *Plant Pathology* 50:10–27. https://doi.org/10.1046/j.1365-3059.2001.00546.x
- Weston L.A. 1996. Utilization of allelopathy for weed management in agroecosystems. *Agron. J.* 88:860–866. https://doi.org/10.2134/agronj1996.00021962003600060004x
- Weston L.A., Duke S.O. 2003. Weed and crop allelopathy. *Crit. Rev. Plant Sci.* 22:367–389. https://doi.org/10.1080/713610861
- Whitehead A.G. 1995. Decline of potato cyst nematodes in spring barley microplots. *Plant Pathology* 44:191–195. https://doi.org/10.1111/j.1365-3059.1995.tb02728.x

## How the planner applies this knowledge (implementation choices)
These choices were made while calibrating the checker on four real farms (Iowa corn–soy, Nevada alfalfa, Kenyan smallholder maize, Andalusian wheat–sunflower). They avoid alarming farmers about textbook rotations while still flagging real problems.

1. **Only rotation-controllable organisms count.** Generalists (Rhizoctonia, Pythium, root-knot nematodes) and the migratory fall armyworm are excluded: changing the crop sequence barely changes them. Wireworms are handled by the cited "after grass/ley" rule rather than their host list.
2. **Regional ranges.** Striga only in Africa/Asia, western corn rootworm only in North America/Europe, broomrape in the Mediterranean, Africa and Asia, cereal stem borers in Africa/Asia, black-grass in Europe.
3. **Risk follows the published break.** *High* means a host grew last year or twice within `break_years`; *medium* means one host year within the break. Only high-severity organisms at high pressure make a year red.
4. **No double counting.** A cited sequence rule (e.g. continuous maize −13 %) replaces the generic return-interval and predecessor-value effects. The combined yield effect is capped at −30 … +15 %.
5. **Perennial stands.** Alfalfa continuing as the same stand is not "alfalfa after alfalfa". Autotoxicity applies when re-seeding. Stands older than five years get a stand-age warning.
6. **Realistic alternatives.** The optimiser only proposes crops of the field's cropping system (temperate, irrigated arid, Mediterranean, tropical), plus the farmer's own crops. It keeps the farm's staple crop in the rotation, and only suggests vegetables, roots/tubers or perennial forage if the farm already grows that kind of crop.
7. **Cover crops by climate.** Rye/vetch, phacelia or mustard in temperate climates; quick legumes (mung bean, cowpea) in the tropics. A cover never shares a family or pathogen with the next cash crop (e.g. no mustard before canola: clubroot and blackleg).
