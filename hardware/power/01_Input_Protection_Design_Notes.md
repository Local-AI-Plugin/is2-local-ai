# 01_Input_Protection — Design Notes

Sheet: `01_Input_Protection.SchDoc` · Basis: 12 V / 3 A / 36 W continuous output · Battery: 16S LiFePO4

Every number is tagged:
**[MFR]** manufacturer spec · **[DEC]** project decision · **[TGT]** design target ·
**[ASM]** preliminary assumption · **[CALC]** calculated · **[TBD]** must be verified

Primary reference: TI *TPS4811-Q1* datasheet, SLUSEE5E (Rev. E, April 2026), which covers TPS48110-Q1 and TPS48111-Q1.

---

## 1. Input envelope

| Quantity | Value | Tag | Source |
|---|---|---|---|
| Nominal pack | 51.2 V | [ASM] | 16 × 3.2 V |
| Full charge | 58.4 V | [ASM] | 16 × 3.65 V |
| BMS overvoltage trip | ~60 V | [ASM] | Typical LiFePO4 OV of ~3.75 V/cell × 16. **[TBD] read the real setting from the JBD SP17S005 config** |
| Minimum operating | 40 V | [ASM] | Not frozen. Set by the cell datasheet and the BMS UV setting |
| Continuous input current @ 40 V | 0.96 A | [CALC] | 36 W / (40 V × 0.94) |
| Continuous input current @ 51.2 V | 0.75 A | [CALC] | 36 W / (51.2 V × 0.94) |

**Max normal input to design around: 60 V** [ASM]. That is the highest voltage the BMS will pass before it trips, so every part on the input must work continuously at 60 V.

---

## 2. Controller limits (TPS48111-Q1)

| Parameter | Value | Tag |
|---|---|---|
| VS operating range | 3.5–80 V | [MFR] §6.5 |
| VS, CS+, CS−, ISCP to GND, abs max | −1 to 100 V | [MFR] §6.1 |
| VS, CS+, CS− to SRC, abs max | −60 to 100 V | [MFR] §6.1 |
| CS+ to CS−, abs max | ±0.3 V | [MFR] §6.1 |
| Slew rate on drain-side pins (VS, CS+, CS−, ISCP) | 60 V/µs max | [MFR] §6.1. **[TBD] confirm the unit in the PDF; the text extract dropped the µ** |
| UVLO rising / falling | 1.18 V / 1.11 V typ | [MFR] §6.5 |
| Short-circuit turn-off | 1.2 µs | [MFR] (TPS48111-Q1) |
| **Overvoltage pin** | **None on TPS48111-Q1** (only TPS48110-Q1 has OV) | [MFR] Table 5-1 |

Consequences:
- **No hardware overvoltage cutoff.** With TPS48111-Q1, any surge the TVS lets through reaches `PROTECTED_HV` and the buck. See §8.
- **The shunt goes on the input (drain) side of the FETs.** The datasheet lists VS/CS+/CS−/ISCP as "drain side input pins", and RSET connects VS to CS+. The block diagram in the handoff (shunt after the FETs) is **wrong for this controller**. Copy datasheet Figure 9-14 (back-to-back FETs with pre-charge, driving DC-DC converter loads).

### Corrected block order
```
J1 → F1 → D1 (TVS) → RSNS (CS+/CS−) → Q1 (main) → Q2 (reverse block, common-source with Q1) → PROTECTED_HV
                                 └→ Q3 + R_PRE (pre-charge path, driven by G / INP_G) ┘
```
Pin connections follow Figure 9-14 exactly. **Do not wire FET orientation from memory.**

---

## 3. F1 — input fuse

F1 is backup protection for the PMS board and cable. It is not battery protection; the BMS handles that.

| Requirement | Value | Tag | Reasoning |
|---|---|---|---|
| DC voltage rating | ≥ 80 V DC (prefer ≥ 100 V DC) | [DEC] | Must interrupt at full pack voltage plus margin. Many SMD fuses are rated only 32/63 V DC, so reject those |
| Rated current | 3 A, time-lag | [TGT] | About 3× the 0.96 A worst-case continuous draw. Must not open on ROCK load steps or pre-charge |
| Breaking capacity | ≥ BMS short-circuit current at 60 V | [TBD] | Get the BMS short-circuit trip level from the JBD spec |
| I²t | Above the pre-charge pulse I²t (§7) | [TBD] | Check once C_IN and R_PRE are fixed |

The fuse should only blow if the TPS48111 or the FETs fail short. Normal overcurrent is handled by the controller's OCP/SCP settings (§5).

---

## 4. D1 — TVS

| Requirement | Value | Tag |
|---|---|---|
| VRWM (standoff) | ≥ 60 V | [CALC] from §1. Must not conduct at the BMS OV limit |
| Clamp at the expected surge current | < 100 V | [MFR] Abs max on VS/CS±; also the FET VDS limit |
| Placement | J1/F1 side, before RSNS; short, wide loop to PGND | [MFR] §9.5 |

Candidate class: a **60 V-standoff unidirectional TVS** (e.g. SMBJ60A / SMCJ60A family) [TBD — verify on the chosen vendor's datasheet]. Typical JEDEC values for this class are VBR(min) ≈ 66.7 V and VC ≈ 96.8 V **at the full rated pulse current**.

**Margin check:** 96.8 V vs 100 V abs max leaves only ~3%, and only at the rated pulse current. In this system the realistic surge is the cable-inductance kick when the FETs turn off under a short circuit (E = ½·L·I², tens of µJ for ~1 µH and ≤ 10 A). At that low current the TVS clamps nearer VBR (~70–75 V), well inside 100 V. **[TBD] confirm with an LTspice/TINA run using the real cable length and ISC setting.**

Also from §9.5:
- RVS ≈ 100 Ω + CVS filter into the VS pin [MFR recommendation]
- 1 nF across ISCP–CS− near the IC [MFR recommendation]
- TI recommends a diode/TVS on the output against negative spikes. The handoff did not have this, so add a footprint for it.

---

## 5. RSNS, RSET, OCP / SCP / IMON

Datasheet equations (SLUSEE5E):
- Eq. 6: `RIWRN = 11.9 × RSET / (RSNS × IOC + VOS_SET)`
- Eq. 11: `RISCP = (ISC × RSNS) / 15.6 µA − 464 Ω`
- Eq. 12–13: `VIMON = (VSNS + VOS_SET) × Gain`, `Gain = 0.9 × RIMON / RSET`

Sanity check against the datasheet tables: RSET = 100 Ω, RIWRN = 39.7 kΩ → 30 mV ✓; RISCP = 2.1 kΩ → 40 mV ✓.

| Item | Value | Tag | Reasoning / calc |
|---|---|---|---|
| IOC (overcurrent, timed trip) | 2.5 A | [TGT] | 2.6× the 0.96 A worst-case continuous. Leaves room for ROCK transients above 3 A out |
| ISC (short circuit, 1.2 µs trip) | 5 A | [TGT] | 2× IOC |
| RSET | 100 Ω, 1% | [MFR] | Recommended range 50–100 Ω; 100 Ω matches the datasheet's characterization |
| RSNS | 10 mΩ, 1%, ≥ 0.25 W, Kelvin | [CALC] | VSNS = 25 mV at IOC, 50 mV at ISC; under the ±0.3 V CS± limit. P = 1² × 0.01 = 10 mW continuous |
| RIWRN | 47.5 kΩ (E96) | [CALC] | 11.9 × 100 / (0.010 × 2.5) = 47.6 kΩ |
| RISCP | 2.74 kΩ (E96) | [CALC] | 0.050 / 15.6 µA − 464 = 2.74 kΩ |
| RIMON | 7.32 kΩ (E96) | [CALC] | Target 3.3 V at ISC = 5 A (MCU ADC full scale). Gain = 3.3 / 0.050 = 66 → RIMON = 66 × 100 / 0.9 = 7.33 kΩ |
| IMON scale | ≈ 0.66 V/A | [CALC] | 0.010 Ω × 65.9 |
| CTMR (OC delay) | TBD | [TBD] | Set from the ROCK's measured load-step duration (TI example: 68 nF ≈ 1 ms) |

IMON accuracy at 1 A (VSNS = 10 mV) is roughly ±2–5% per §6.5 [MFR]. That is good enough for J/query and efficiency logging, but the main telemetry should still come from a dedicated power monitor on `04_Power_Sensing`.

---

## 6. UVLO divider (EN/UVLO)

`VIN_fall = 1.11 V × (1 + R1/R2)`, `VIN_rise = 1.18 V × (1 + R1/R2)` [MFR thresholds]

| Item | Value | Tag |
|---|---|---|
| Target falling threshold | ≈ 40 V | [ASM] Follows the unfrozen 40 V minimum |
| R2 | 24.9 kΩ, 1% | [DEC] Same as the TI example |
| R1 | 866 kΩ, 1% | [CALC] R1/R2 = 40/1.11 − 1 = 35.0 → 872 kΩ → nearest E96 866 kΩ |
| Resulting fall / rise | 39.7 V / 42.2 V | [CALC] |
| Leakage error | ≈ 0.3 V at input | [CALC] 320 nA max × (R1‖R2 ≈ 24.2 kΩ) × 35.8 |

Decision still open: should the PMS UVLO sit **above** the BMS UV cutoff, so the PMS shuts down cleanly first? Recalculate R1 once the BMS UV setting is known.

---

## 7. Pre-charge (Q3 + R_PRE)

Equations (SLUSEE5E Eq. 25–27): `R_PRE = VIN / I_INRUSH`, `P_peak = VIN² / R_PRE`, `E = ½·C·VIN²`

| Item | Value | Tag |
|---|---|---|
| C_IN (buck input capacitance) | **TBD** | Comes from the `02_Main_GaN_Buck` design |
| I_INRUSH | 0.5 A | [TGT] Same as the TI example |
| R_PRE @ 60 V | 120 Ω | [CALC] |
| P_peak | 30 W | [CALC] Size the resistor for this pulse, not the average |
| Energy per charge, example C_IN = 47 µF | 85 mJ | [CALC] Placeholder until C_IN is known |

---

## 8. Open conflict — buck input rating vs. TVS clamp

- TPS48111-Q1 has **no OV cutoff**, so `PROTECTED_HV` can reach the TVS clamp voltage during a surge.
- LM5148 input is rated **3.5–80 V** [MFR, TI product page]. An 80 V part directly behind a TVS that clamps around 70–97 V is **not acceptable** (handoff rule 11).

Options (pick one before starting `02_Main_GaN_Buck`):
1. **Use a 100 V-class buck controller** (keeping the 100 V GaN stage) so the whole HV bus is 100 V-rated. Cleanest. [TBD: candidate selection]
2. **Switch to TPS48110-Q1**, which has a hardware OV pin, and build pre-charge another way (loses the G driver).
3. Keep TPS48111-Q1 and add an external OV comparator that drives INP low (slower, more parts).

Recommendation: **option 1**.

---

## 9. MOSFETs (Q1, Q2, Q3)

| Requirement | Value | Tag |
|---|---|---|
| VDS | 100 V | [DEC] TVS clamp can reach the high 90s V. TI's 48 V example uses 80 V FETs, which is not enough with 60 V max input |
| VGS max | ≥ ±20 V | [MFR] Gate drive is BST–SRC ≈ 12 V |
| RDS(on) | ≤ ~20 mΩ is plenty | [CALC] 1 A² × 20 mΩ = 20 mW |
| SOA | Must survive ISC (5 A) at 60 V for 1.2 µs, plus Q3 during pre-charge | [TBD] Check the SOA curves |
| CBST | ≥ 4 × Qg(total) / 1 V | [MFR] Eq. from §9.3.2 |

Specific part numbers: TBD.

---

## 10. J1 footprint verification checklist (Molex 43045-0213)

Read from `Libraries/430450213/CONN_SD-43045-005_02_MOL.PcbLib` (SnapEDA source):

| Feature | Footprint has | Check against the Molex drawing | ✓ |
|---|---|---|---|
| Pin 1 → pin 2 | 3.00 mm, single column (0,0) → (0, 3.00) | Row pitch 3.00 mm | ☐ |
| Pin hole / pad | Ø1.067 mm plated / Ø1.575 mm | Recommended PCB hole | ☐ |
| Locating holes | 2 × Ø1.067 mm NPTH at (±3.00, 3.94) | Molex lists this part as having a *PCB polarizing peg*. Confirm the count, size and position of the peg hole(s). **Most likely error** | ☐ |
| Pin 1 side | Pin 1 at origin | Relative to latch / housing | ☐ |
| Silkscreen | Small circles at (4.6, 0) | Matches the body outline? | ☐ |
| 3D body | **None** | Attach the `.STP` and check it lines up with the pads | ☐ |
| Current rating | 5 A/contact (series value, unconfirmed) | Confirm on the drawing; well above 1 A in any case | ☐ |

Sources: Molex part detail / sales drawing for 43045-0213 (molex.com).
