# Hackathon presentation (ScienceClaw, 3 minutes)

| File | What it is |
|---|---|
| `slides.html` | 7 slides, 16:9 (1920×1080 stage, scales to any window), fully offline, single file (1.8 MB). |
| `demo/index.html` | ~77 s auto-playing captioned walkthrough (20 frames in `demo/img/`). Opens from disk. |
| `judging_criteria.md` | Event goals, exact rubric, slide/demo → criteria map, and honest gaps. |
| `build/` | `build.py` + `slides_template.html` (rebuild slides from records), `quoted_numbers.json` (every number on the slides, for checking). |

## Presenting

- **Slides:** open `slides.html`. → / Space / PageDown next, ← / PageUp back, Home/End, click right ¾ of a slide = next,
  left ¼ = back. **N** toggles speaker notes (with timing: 22+32+25+23+28+30+20 = 180 s). **F** fullscreen. `#5` in the
  URL jumps to a slide. Slide 5 has an interactive 3D brain: drag to rotate, wheel to zoom, buttons switch
  before / after ablation / after pulse-train stimulation / TI field.
- **Demo:** open `demo/index.html` and press Play (or append `?autoplay`). Space pauses, arrows step.

## Rebuilding

```
.venv-model/Scripts/python.exe presentation/build/build.py      # slides from ledgers + A0038 + anatomy
python -m http.server 8771 --bind 127.0.0.1 --directory presentation   # needed only for capture
python presentation/demo/capture.py                              # headless Chrome over CDP, needs 8765/8770/8771 up
python presentation/demo/build_demo.py                           # demo/index.html from frames.json
```

All inputs are read-only: study ledgers, `studies/study-002/artifacts/A0038-SimulationBatch`, `data/wang-co2-ana`
(patient 2 cortex, region map, contacts), `data/wang-5367ef4/data/EMF`, and nilearn's bundled fsaverage5.
No vault or truth file is read. The capture only switches dashboard tabs and opens a skill read-only (no Save).

## Claims the records do not (fully) support, and how the deck handles them

- "~1 in 3 people with epilepsy are drug-resistant" is background from the literature (Kwan & Brodie 2000; Chen
  et al. 2018), not a study record; the slide says so.
- No single-agent baseline exists. Slide 3 shows a ledger proxy (producer-only vs independently gated) and says so.
- Study-002 results are exploratory: model not qualified, primary window without baseline seizures, baseline not
  matching the recording, high-amplitude pulse trains numerically failed, 9 bilateral regions ablated, vault unopened.
  All on slide 6.
- The TI field is shown on the fsaverage5 template only; mapping onto Patient 2 is open need N001.
- A0038 and the other study-002 R4 artifacts are still *unreviewed* (no R5 gate yet) at capture time.
