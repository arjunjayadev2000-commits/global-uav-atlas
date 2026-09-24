# Submission folder - CDM Datathon-2026 (Theme 6.1)

## Phase I - email to datathon.ids@gov.in by 30 Sep 26 (Gen Instr Para 8.2)

| # | File | Required by | Status |
|---|---|---|---|
| 01 | `01_Email_Draft.txt` | covering mail | Ready: fill in rank, service no, unit, mobile |
| 02 | `02_Appendix_A_Individual_Details.docx` | Para 8.1 / 8.2 personal details | Fill in the [bracketed] fields |
| 03 | `03_..._Booklet_(Main_Submission).pdf` | Para 8.2: analysis in PDF, with software screenshots (Annex C) | Ready; add the Power BI screenshots, then rebuild |
| 04 | `04_..._Satellites.pbix` | Para 8.2: output in Power BI (*.pbix) only | **To do**: follow `Supporting/POWERBI_BUILD_GUIDE.md` |

Before sending:
- [ ] Rank, Service No and Unit are filled in:
  - on the booklet title page (the `RANK / SERVICE_NO / UNIT` lines in `report/build_booklet.py`, or edit the Word file and save it as PDF);
  - in Appendix A;
  - in the email;
  - on the first slide.
- [ ] The four Power BI screenshots are in Annex C.
- [ ] The .pbix reopens cleanly.
- [ ] If you are also submitting Theme 6.2, send each theme in its own email with its own subject line.

## Phase II - presentation by the top 10 at CDM (02-07 Nov 26)

- `Phase_II_Presentation/` has the 17-slide PowerPoint, with speaker notes in the file, and a text copy of the notes. Carry it on a pen drive.
- Before the day, refresh the live numbers with `analysis/run_all.py` after pulling a fresh catalogue:
  - Starlink count;
  - working satellites;
  - ORBITWATCH status.
- Likely questions:
  - Why a name-based ISR count? It is a transparent lower bound; covert satellites only widen the gap.
  - Is the collision-risk index a probability? No, it is a relative index (2014 = 1).
  - How good is the forecast? It was back-tested at 8.6% error, and two independent routes agree.

`Supporting/` holds material you need not send but should keep ready: the Word booklet, the annotated code, the Power BI tables and the build guide.
