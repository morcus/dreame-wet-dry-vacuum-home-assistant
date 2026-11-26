# H15 Pro Heat mapping — work in progress

Model `dreame.hold.w2449e`; app common plugin 728, resource 7, firmware snapshot 2.1.8_1047. **Sensor mapping remains incomplete.** This validation build is tracked in the draft PR while awaiting Dreame engineering feedback. Definitions and write plans live in the existing `const.py`; exporter in `api.py`; entities in the existing platforms. H14 definitions are preserved.

## App feature coverage

| Feature | Home Assistant behavior | Evidence / remaining work |
|---|---|---|
| Cleaning / suction / water / custom heat | Selects, app-coupled write batches | Existing enum captures plus app; physical write tests pending |
| Self-cleaning / drying preferences | Selects; synchronized manual/return/scheduled copies | App PopWashDry / washDryKeyMap |
| Start / resume / stop self-cleaning | Commands 2/3/4 for selected wash, 1 resume, 0 stop | App isNeedCorrectOperation=true; live task test pending |
| Start / stop drying | Setting 1 sends 1; setting 3 sends 4; stop sends 0 | App drySetValueMap; live task test pending |
| Filter / roller life reset | Set 19.1=1 / 6.1=1, then read telemetry | App MaterialDetailPage; live reset pending |
| Optional rear roller | Reset 7.1=1 only with nonnegative remaining life | Current 7.7=-1: unavailable |
| Water / tank / brush / filter alerts | 28 field-specific binary alerts; raw warn/error retained | App warnVersion=2; dirty-tank-full bit 4096 now live-confirmed; clean-tank capture still needed |
| GlideWheel / lifting arm / smart drying | Selects and switches with preserved arm bits | App definitions; live writes pending |
| Default hot-water temperature | Select 25.1=1/2/3 | App PopHotWater |
| Voice language | Installed languages 2/3/4/6/7/16/17 | Resource holdPluginVoiceType=4 / DATA_VOICE4 |
| Voice volume | Three-position slider: 0 Silent / 1 Low / 2 High → raw 0/30/60 | Actual VoiceSettingPage slider levels |
| Wash/dry schedule | Time in minutes after midnight, presets and seven weekday switches | App decimal weekday encoding; device timezone; live writes pending |
| Forward / backward | 0.3 s pulse, explicit stop, horizontal + online guards | isSupportControlS=true; live test pending |
| Left/right and diagonal movement | Diagnostic only | isSupportControl=false |
| Brush light / electrolysis / brush speed | Diagnostic only | Not exposed by w2449e app resource |
| Cleaning history | Existing raw properties / mapped duration and progress | Complete event-history retrieval remains unimplemented |
| Firmware / account management | Dreame app | Outside this control build |

## State and write semantics

H15 commands do not overwrite telemetry or invent reset counters. Responses must acknowledge every requested property with success; `value=-1`, absent/partial rows and errors fail. Commands read state afterward; later MQTT/polls supply authoritative values. Read-modify-write for arm/schedule days is serialized and preserves sibling settings.

Self-cleaning starts only while idle on dock with at least 20% battery and a known wash preference. Drying cannot start during cleaning. Stop and resume buttons follow the current task state. Forward/backward is bounded and sends stop even after a rejected start or cancellation. Six-direction robot controls are not assumed from the common plugin.

Schedule uses eight **decimal digits**, not binary bits: once at 10^7; Sunday at 10^6; Monday–Saturday at 10^0–10^5. Invalid digits remain unknown and cannot be modified as weekdays. A new schedule requires a configured start time; disabling it does not fabricate a different time.

Warning/error fields use the exact app table and JavaScript integer-key iteration order. Roller fault codes are multi-bit values, not simple on/off bits. Unknown bits and physical tank conditions are never cleared by writing a sensor value. App dismissals are UI-only, not device reset commands.

## Evidence levels

`confirmed` means an observed enum matched the app; `plugin` means source-derived but still awaiting corresponding live verification; `candidate` and `unmapped` retain raw data. None of these labels implies a physical write has already been tested.

## Property catalog

| Property | Name | Evidence | Values / units |
|---|---|---|---|
| `1.1` | Self-cleaning command raw | plugin | Raw |
| `1.2` | Self-drying command raw | plugin | Raw |
| `1.3` | Roller brush head light raw | plugin | Raw |
| `1.4` | Auto detergent mixing raw | plugin | Raw |
| `1.6` | Altitude setting raw | plugin | 0=Standard altitude; 1=High altitude |
| `1.7` | Return to automatic wash & dry | confirmed | 0=On; 1=Off |
| `1.8` | Self-cleaning mode | plugin | 2=Standard Immersive Self-Cleaning; 3=Deep-Clean Immersive Self-Cleaning; 4=Smart Self-Cleaning; 5=Hot-Water Self-Cleaning |
| `1.9` | Auto roller brush drying | plugin | 0=On; 1=Off |
| `1.10` | Drying mode | confirmed | 1=High-Speed; 3=Super-Speed |
| `1.11` | Timed drying after cleaning | plugin | Raw |
| `1.12` | Scheduled drying time raw | plugin | Raw |
| `1.13` | Scheduled drying repeat raw | plugin | Raw |
| `1.14` | Voice volume | plugin | % |
| `1.17` | Voice language pack | plugin | 2=English; 3=German; 4=French; 6=Italian; 7=Spanish; 16=Dutch; 17=Portuguese |
| `1.28` | Work state | confirmed | 1=Power on; 2=Power off; 3=Standby; 4=Charging; 5=Self-cleaning; 6=Self-drying; 7=Sleeping; 8=Convenient; 9=Adding clean water; 10=Washing paused; 11=Cleaning paused; 12=Drying paused; 13=OTA upgrading; 14=Voice upgrading; 15=Charging complete; 16=Auto cleaning; 17=Degerming; 18=Water suction; 19=Quiet cleaning; 20=Quick cleaning; 21=Strong cleaning; 22=Personalized cleaning; 23=Fast drying; 24=Faster drying; 25=Quiet drying; 26=Fast self-cleaning; 27=Deep self-cleaning; 28=Smart self-cleaning; 29=Convenient paused; 30=Fast self-cleaning paused; 31=Deep self-cleaning paused; 32=Fast self-cleaning drying; 33=Deep self-cleaning drying; 34=Smart self-cleaning drying; 35=Retry drying; 36=Retry self-cleaning; 37=Smart self-cleaning paused; 40=Power mode; 41=Hot water cleaning; 42=Hot water self-cleaning; 43=Hot water self-cleaning paused |
| `1.29` | Self-cleaning progress | plugin | % |
| `1.30` | Self-drying progress | plugin | % |
| `1.47` | Last-clean timestamp candidate | candidate | Raw |
| `1.53` | Total working time | plugin | min |
| `1.54` | Clean count | plugin | Raw |
| `1.55` | Start time | plugin | Raw |
| `1.56` | Self-drying task duration | plugin | s |
| `1.57` | Self-cleaning task duration | plugin | s |
| `1.64` | Last clean mild-dirt time raw | candidate | Raw |
| `1.65` | Last clean moderate-dirt time raw | candidate | Raw |
| `1.66` | Last clean severe-dirt time raw | candidate | Raw |
| `1.67` | Cleaning solution ratio mode | plugin | 2=Smart Mode; 3=Powerful stain removal |
| `1.75` | Scheduled wash & dry mode | plugin | 4=Auto-Adjust; 2=Standard; 3=Deep-Clean |
| `1.76` | Scheduled wash and dry time | plugin | Raw |
| `1.77` | Scheduled wash and dry repeat | plugin | schedule |
| `1.81` | Return self-cleaning wash mode | plugin | 4=Auto-Adjust; 2=Standard; 3=Deep-Clean |
| `1.82` | Return self-cleaning dry mode | plugin | 1=High-Speed; 3=Super-Speed |
| `1.83` | Scheduled self-dry mode | plugin | 1=High-Speed; 3=Super-Speed |
| `2.1` | Cloud status code raw | candidate | Raw |
| `3.1` | Battery | confirmed | % |
| `4.1` | Warnings | plugin | warnings |
| `4.2` | Errors | plugin | errors |
| `4.3` | Warning push raw | plugin | Raw |
| `4.5` | Raw 4.5 | unmapped | Raw |
| `4.6` | Dirty water tank status | confirmed | 0=Normal; 81=Full; other values unknown |
| `4.7` | Raw 4.7 | unmapped | Raw |
| `4.38` | Raw 4.38 | unmapped | Raw |
| `4.83` | Raw 4.83 | unmapped | Raw |
| `6.6` | Roller brush maximum life raw | plugin | min |
| `6.7` | Roller brush remaining | confirmed | min |
| `7.6` | Rear brush maximum life raw | plugin | min |
| `7.7` | Rear brush remaining raw | plugin | min |
| `10.1` | Dip angle level | plugin | Raw |
| `13.2` | Electrolyzed water setting raw | plugin | Raw |
| `16.1` | Suction setting | confirmed | 1=Gentle; 2=Standard; 3=Strong |
| `16.2` | Water level | confirmed | 1=Low / legacy; 2=Standard; 3=High |
| `16.3` | Electrolyzed water raw | plugin | Raw |
| `16.4` | Brush speed raw | plugin | Raw |
| `16.6` | Personalized mode flag | plugin | Raw |
| `16.7` | Cleaning mode | confirmed | 1=Quiet; 3=Turbo; 4=Personalized |
| `16.8` | Hot water mode | confirmed | 0=Off; 1=Mild; 2=Standard; 3=Thermal |
| `19.2` | Filter maximum life raw | plugin | min |
| `19.3` | Filter remaining | confirmed | min |
| `20.2` | Dust bag maximum life raw | plugin | min |
| `20.3` | Dust bag remaining raw | plugin | min |
| `21.6` | Suction brush maximum life raw | plugin | min |
| `21.7` | Suction brush remaining raw | plugin | min |
| `22.6` | Suction filter maximum life raw | plugin | min |
| `22.7` | Suction filter remaining raw | plugin | min |
| `23.1` | GlideWheel traction | plugin | 0=Balanced; 1=Gentle; 2=Turbo |
| `24.1` | Lifting arm modes | plugin | mechanical_arm_2449 |
| `25.1` | Default hot water temperature | plugin | 1=Mild; 2=Standard; 3=Thermal |
| `26.1` | Smart drying | plugin | 0=On; 1=Off |
| `26.2` | Smart moisture protection | plugin | 0=On; 1=Off |
| `26.3` | Roller brush moisture sensitivity | plugin | 2=Low; 3=Medium; 4=High |
| `26.4` | Raw 26.4 | unmapped | Raw |
| `26.5` | Raw 26.5 | unmapped | Raw |
| `100.1` | Remote forward raw | plugin | Raw |
| `100.2` | Remote backward raw | plugin | Raw |
| `100.3` | Remote left raw | plugin | Raw |
| `100.4` | Remote right raw | plugin | Raw |
| `100.5` | Remote left-back raw | plugin | Raw |
| `100.6` | Remote right-back raw | plugin | Raw |

## Remaining telemetry validation

The earlier clean-tank-removal export was taken at 2026-10-07T17:21:37Z from integration 0.2.1. It reports Sleeping (1.28=7), zero warnings/errors (4.1/4.2/4.3=0), no mapping changes and no direct live properties. It cannot establish a tank-missing mapping. The new 4.83=-1 is retained as unknown.

The H15-only server snapshots show `4.6=0` in two normal-state captures, `4.6=81` when the app showed “Used water tank is full” and `4.2=4096`, then `4.6=0` and `4.2=0` in the 2026-10-08 export after the alert cleared. This confirms only the observed state values: `0=Normal`, `81=Full`; other values remain unknown, and no percentage is assigned. `4.5=[81]` and `4.7=[3]` stayed unchanged across these snapshots, so neither is mapped as clean-water nor suction status. `1.14` (volume) is absent from these server snapshots and the direct-read list is empty, so its current state cannot be read from this capture; do not report an invented default. Compare app changes one at a time with an awake device.

Task duration fields 1.56/1.57 are seconds used by the app's remaining-time calculation, not lifetime totals. Work time 1.53 is minutes; start time 1.55 is epoch seconds. Consumable life remains minutes, with hours/percentage derived only from actual reported maximum life on H15.

## Diagnostic workflow

Refresh mapping before and after a single change. Export `metadata_share.json` (current manifest version) for source profile, raw properties and exact differences. No cloud credentials are needed for unit tests; the user performs device and full Home Assistant validation before considering the implementation ready for release.


## Mode dropdown audit (work in progress)

Daily controls expose 11 primary selects. Return/scheduled copies, the duplicated arm combination select and unobserved global hot-water property are not registered as separate primary controls. Four arm switches preserve the reserved bit. Work state (1.28) remains telemetry; it is not writable merely because its name contains "mode".

Main-page wash/dry selection writes all six properties together (1.8/1.10, 1.81/1.82, 1.75/1.83), preserving the companion preference. Advanced schedule writes update only 1.75/1.83. An unknown companion is never guessed. Quiet/Turbo presets remain selectable with hot water as in TimeZonePage; manual suction is unavailable while hot water is enabled. Suction/water controls are shown only within enabled Personalized mode.

Validation covers H14 table preservation and the supplied dirty-tank-full capture. Commands still require physical-device validation. This remains a draft build with incomplete sensor mapping.

## Native device presentation (work in progress)

Single device, unchanged identifiers. H15 daily controls have no entity category, general telemetry remains primary sensors, maintenance counters/reset buttons and alerts use Diagnostic. No H15 entity remains in Configuration. HA owns card headings; Diagnostic cannot be renamed Maintenance by the integration. Unresolved/duplicate raw sensors are optional disabled diagnostics, with a one-time reversible registry migration. H14 categories/mappings are unchanged.

Voice volume remains a NumberMode.SLIDER with min=0, max=2, step=1. Levels 0/1/2 encode raw 0/30/60, confirmed against VoiceSettingPage's 0..60, step=30 slider and direct PropVolume write. UI scale is a level, not a percentage. English/French/Hebrew names explain the three positions; attributes expose the level label and raw value. Write acknowledgement rejection does not change the displayed level, and unknown raw values are not rounded to a known level.

### Consumable percentage display

Separate H15 remaining-percentage sensors preserve the existing duration entities and their statistics. Like the supplied Dreame plugin, the percentage is truncated: `remaining_minutes * 100 // maximum_minutes`. Maximums are read from 6.6 (front roller) and 19.2 (filter); no assumed H14/60-hour fallback is used for H15. Missing or invalid maximums remain unknown. The card prefers percentage sensors automatically, preserves explicit manual choices, and marks 0–10% as requiring maintenance. Full sensor mapping and physical device verification remain incomplete.

## Source audit — 2026-10-08

Reviewed the account-provided common plugin 728 and w2449e resource package 7, together with the official H15 product support page. No public complete SIID/PIID specification was found. Direct retrieval of the supplied cloud plugin URL returned HTTP 403; this audit does not claim a newly downloaded or latest plugin. Native phone-app access was unavailable.

The comparison above also shows that reported integer fields arrive successfully through `iotstatus/props`; `get_properties` may provide the same values as strings. The client now normalizes SIID, PIID, result code and value (including list-valued fields) before merging live reads over the cloud cache. Its read request rows include the per-property DID, matching Dreamehome `Model.getProps`. Write acknowledgements also normalize numeric strings such as `"0"`; rejection logs include only response codes and row counts, not credentials or tokens.

The supplied resource ZIP MD5 is `68ce3a5e178d6a49c4a432cd6b6fce13`, matching the account export. The plugin ZIP does not match the export's original encrypted archive checksum, so that archive identity is not claimed. Reviewed extracted bundle SHA256: `589c87feb80582456f3b1793c0091896bb14e22a0542378fff2fc2c5a1f89548`; config SHA256: `ee3a867471be3342266de0b1e83e9462514693e03d169362464582f98ef2226e`.

| Source in extracted app | Verified behavior used by this build |
| --- | --- |
| VoiceSettingPage slider and completion handler | min 0, max 60, step 30; direct volume write |
| Main-page `_handleSoakWashResult` | Six wash/dry properties in one batch |
| Advanced-page `_handleSoakWashResult` | Scheduled wash/dry pair only |
| TimeZonePage `onCustomModePress` | Quiet=power1/water2; Turbo=power3/water3; Personalized=power2 or hot power1/water2 |
| w2449e `config.json` | No electrolyzed-water UI; model-specific supported controls |
| Model `createSetPropReq` | Every `set_properties` row includes the device DID, SIID, PIID and value; the H15 request now follows this format |

Research fields stay in mapping exports without creating a sensor for every returned key. Confirmed dirty-tank state (4.6) is exposed with primary maintenance telemetry; tank/accessory alerts are separate entities; other decoded messages remain in aggregate warning/error attributes and the card. A one-time migration disables redundant H15 entries without deleting history. H14 is unaffected. Dashboard model selection supports H15/H14/auto and registry-based renamed-entity matching; manual selections remain available.

## H15 full property crosswalk — 2026-10-08

This section compares the uploaded `metadata_share(3).json` with the account-provided app/resource package and the current H15 integration profile. The export is from model `dreame.hold.w2449e`, firmware `2.1.8_1047`, integration `0.2.2`; its mapping profile has 78 property definitions, 37 with a reported value, and the server returned 50 property keys total. Thirteen returned keys are not in the profile and remain raw. A property definition is not necessarily a Home Assistant sensor: commands, settings, telemetry, and hidden research properties all use SIID.PIID identifiers.

| Function | H15 properties in scope | Mapping and latest server value | Relations / HA behavior |
|---|---|---|---|
| Device status | `1.28`, `2.1`, `3.1` | Work state `1.28=7` → Sleeping; cloud status `2.1=7`; battery `3.1=100%` | `2.1` mirrored `1.28` in captures. Work state and battery are read-only; online/charging are separate connection-derived binary entities. |
| Self-clean / drying commands | `1.1`, `1.2` | Plugin command properties; not sensor-state controls | Dedicated buttons start/resume/stop. Their values are not exposed as writable raw sensors. The selected wash/dry mode supplies the command argument. |
| Wash & dry settings | `1.7`–`1.13`, `1.75`, `1.81`–`1.83` | `1.7=1` (auto return Off); `1.10=3` (Super-Speed); `1.12=-1`, `1.13=-1`; other keys not returned | Main selection `1.8/1.10` synchronizes return preferences `1.81/1.82` and scheduled preferences `1.75/1.83`. `1.9` is auto roller drying; `1.11` enables timed drying; `1.12/13` hold time/repeat. |
| Wash/dry enum options | `1.8`, `1.10`, `1.75`, `1.81`–`1.83` | Wash plugin values: `2=Standard`, `3=Deep-Clean`, `4=Auto-Adjust` (plugin internal Smart); `5=Hot-Water` is plugin-known but not offered in the primary dropdown. Dry: `1=High-Speed`, `3=Super-Speed` | Primary wash/dry selects are user controls. Return/schedule copies are synchronized internally; work state `1.28` is status only, not a mode selector. |
| Voice | `1.14`, `1.17` | Not returned in latest export | The uploaded mapping profile incorrectly labels volume with unit `%`; the app control is a three-step level slider, not a percent. HA 0/1/2 = Silent/Low/High, raw 0/30/60. Voice-language IDs from plugin: 2 English, 3 German, 4 French, 6 Italian, 7 Spanish, 16 Dutch, 17 Portuguese; installed pack selection not physically verified. |
| Operation / history | `1.28`–`1.30`, `1.47`, `1.53`–`1.57`, `1.64`–`1.66` | `1.29=0%`, `1.30=0%`, `1.47=1789398952` candidate timestamp, `1.54=44`, `1.56=2429s`, `1.57=353s`, `1.64=231`, `1.65/66=0`; 1.53/55 absent | `1.29` links to clean-task duration `1.57`; `1.30` to dry-task duration `1.56`. 1.64–66 are mild/moderate/severe dirt durations; their units remain unknown. 1.53 is cumulative working minutes; 1.55 start epoch seconds per app code. |
| Scheduled cleaning | `1.76`, `1.77` | `1.76=0`, `1.77=0` | HA number is minutes after midnight with minute steps; device property is seconds after midnight. Repeat supports common presets and weekday switches. They form one schedule; don't interpret `1.76` as an independent duration. |
| Detergent mode | `1.67` | Plugin options `2=Smart`, `3=Powerful stain removal`; not returned | Select setting. Neighbor raw IDs `1.68`–`1.73` do not inherit detergent meaning just because they are nearby. |
| Alerts / tank state | `4.1`–`4.7`, `4.38`, `4.83` | Last export: `4.1=0`, `4.2=0`, `4.3=0`, `4.5=[81]`, `4.6=0`, `4.7=[3]`, `4.38=-1`, `4.83=-1` | `4.1/4.2` are H15 warn/error bitfields (`warnVersion=2`) and each feeds several alert entities. The uploaded profile still called `4.6` a candidate; the current code promotes it after the cross-export sequence 0→81 (app used-water tank full; `4.2=4096`)→0. Thus 0=Normal, 81=Full, other values unknown. It is state, not percentage. `4.5/4.7/4.38/4.83` remain unmapped. |
| Primary tank alerts | Derived from `4.1/4.2` | 11 binary entities are registered from the H15 warning/error table | Clean tank: low/empty alert; dirty tank: missing/full/needs cleaning/blocked. Several alert entities share raw `4.1` or `4.2`; all 28 decoded alert definitions are listed in the code. Only dirty-full (`4.2` bit 12) has been directly observed; other meanings are plugin-table mappings. |
| Roller/filter life | `6.6/6.7`, `7.6/7.7`, `19.2/19.3` | `6.7=3413 min`; `7.7=-1`; `19.3=3473 min`; maxima `6.6/7.6/19.2` absent | Remaining minutes pair with maximum-life minutes to calculate %. Since maxima are absent, H15 percentage remains Unknown. `7.7=-1` is unavailable/unsupported. Wear alerts come separately from `4.1`. |
| Optional accessory life | `20.2/20.3`, `21.6/21.7`, `22.6/22.7` | All absent | Plugin-defined dust bag, suction brush and suction filter max/remaining values; don't create an assumed accessory or percentage when absent. |
| Cleaning controls | `16.1`–`16.8` | `16.1=1` Gentle; `16.2=2` Standard; `16.6=1` Custom enabled; `16.7=4` Personalized; `16.8=1` Mild. `16.3/4` absent. | `16.7`: Quiet(1)/Turbo(3)/Personalized(4). Personalized exposes suction `1 Gentle/2 Standard/3 Strong` and water `2 Standard/3 High`; legacy raw water 1 is not offered. Hot water `0 Off/1 Mild/2 Standard/3 Thermal` gates some custom controls. |
| Smart drying | `26.1`–`26.5` | `26.4=1512`, `26.5=1`; `26.1`–`26.3` absent | `26.1` smart dry and `26.2` moisture protection use inverted values (0 On/1 Off); `26.3` sensitivity 2 Low/3 Medium/4 High. `26.4/26.5` unknown. |
| Traction / arm / temperature | `23.1`, `24.1`, `25.1` | Not returned | `23.1`: Balanced(0)/Gentle(1)/Turbo(2). `24.1` bitmask becomes four switches (Smart/Hot Water/Suction/Custom, selected when bit=0); reserved bit preserved. `25.1` plugin-known default hot-water temperature, not a primary HA select. |
| Other model services | `10.1`, `13.2` | `10.1=1`; `13.2` absent | Dip angle is telemetry; electrolysis is plugin-known but disabled in this H15 resource/UI. |
| Remote control | `100.1`–`100.6` | Not returned | Resource disables normal six-direction control. H15 supports only bounded forward/back commands via `isSupportControlS` in the horizontal posture; side directions remain read-only/unavailable. |

### Server keys returned without a mapping profile

These are present in the latest `properties` object, but no H15 meaning is assigned: `1.33=11`, `1.34=0`, `1.35=20`, `1.36=17`, `1.49=5`, `1.50=0`, `1.51=16`, `1.52=11`, `1.68=1`, `1.69=0`, `1.70=200`, `1.71=1`, `1.73=1`. They remain in mapping exports; no HA sensor or guessed labels are added.

### Work-state enum `1.28`

The app/plugin map contains 43 named read-only states: `1 Power on`, `2 Power off`, `3 Standby`, `4 Charging`, `5 Self-cleaning`, `6 Self-drying`, `7 Sleeping`, `8 Convenient`, `9 Adding clean water`, `10 Washing paused`, `11 Cleaning paused`, `12 Drying paused`, `13 OTA upgrading`, `14 Voice upgrading`, `15 Charging complete`, `16 Auto cleaning`, `17 Degerming`, `18 Water suction`, `19 Quiet cleaning`, `20 Quick cleaning`, `21 Strong cleaning`, `22 Personalized cleaning`, `23 Fast drying`, `24 Faster drying`, `25 Quiet drying`, `26 Fast self-cleaning`, `27 Deep self-cleaning`, `28 Smart self-cleaning`, `29 Convenient paused`, `30 Fast self-cleaning paused`, `31 Deep self-cleaning paused`, `32 Fast self-cleaning drying`, `33 Deep self-cleaning drying`, `34 Smart self-cleaning drying`, `35 Retry drying`, `36 Retry self-cleaning`, `37 Smart self-cleaning paused`, `40 Power mode`, `41 Hot water cleaning`, `42 Hot water self-cleaning`, `43 Hot water self-cleaning paused`. Current raw state is `7=Sleeping`.

### Entity visibility and linked readings

In the latest export, the integration creates only its curated H15 entities, not one entity per returned key. General telemetry has 7 values present in this snapshot; 1.53/1.55 are absent. Five maintenance readings are returned (`4.1`, `4.2`, `4.6`, `6.7`, `19.3`); the `7.7=-1` value is filtered as unavailable. Wear-percent entities depend on max-life readings and therefore stay Unknown. Two connection entities and 11 primary binary alerts are separate. `4.6` is now included in maintenance and the card: Normal/Full appear only for verified values; unknown raw values stay Unknown. The clean-water tank still has no verified continuous level sensor.

Local validation after tank-status integration: 49 targeted Python tests and 29 JavaScript device-card tests pass. Seven config-flow tests were excluded because `voluptuous` is missing in the local pytest environment. These are mocked regressions, not a live device/full Home Assistant runtime test. No release tag or manifest version change is assigned.
