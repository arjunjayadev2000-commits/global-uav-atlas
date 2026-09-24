# Submission folder - CDM Datathon-2026 (Theme 6.2)

## Phase I - email submission (Gen Instr Para 8.2) - by 30 Sep 26 to datathon.ids@gov.in

| # | File | Required by | Status |
|---|---|---|---|
| 01 | `01_Email_Draft.txt` | Para 8.2 (covering mail) | Ready - fill in rank, service no, unit, mobile |
| 02 | `02_Appendix_A_Individual_Details.docx` | Para 8.1 / 8.2 "personal details" | Fill in the [bracketed] fields |
| 03 | `03_..._Commanders_Edition_(Main_Submission).pdf` | Para 8.2 "analysis ... in PDF", with software screenshots (Annex C) | Ready; add Power BI screenshots, then rebuild |
| 04 | `04_..._Full_Technical_Report_(Annex).pdf` | Supporting annex (methods, tests, tables) | Ready |
| 05 | `05_..._Supply_Chains.pbix` | Para 8.2 "output files in Power BI (*.pbix) format only" | **To do**: build with `Supporting/POWERBI_BUILD_GUIDE.md` |

Before sending:
- [ ] Rank, Service No and Unit are filled in on both PDF title pages, in Appendix A and in the email. (For the PDFs: edit the
      `RANK / SERVICE_NO / UNIT` lines in `report/build_report.py` and rebuild, or edit the Word files and save them as PDF.)
- [ ] The four Power BI screenshots are in Annex C (send them in the chat, or save them as `figures/pbi_page1-4.png` and rebuild).
- [ ] The .pbix opens on another PC (close and reopen it once).
- [ ] Total attachment size: the PDFs are about 8 MB and the .pbix about 5-15 MB. If the mail server rejects it, send two mails:
      (1) email + Appendix A + main PDF + .pbix, (2) the technical report annex, with the same subject line plus "(2 of 2)".
- [ ] Send well before 30 Sep 26 and keep the "sent" copy.
- Do **not** attach the self-assessment sheet; it is for your own use.

`Supporting/` holds material you are not asked to send but should keep ready: the editable Word versions,
the annotated source code, the Power BI tables and the build guide. If the panel asks for the code, send the code zip.

## Phase II - presentation by the top 10 at CDM (Para 8.4, 9: 02-07 Nov 26)

- The deck (19 slides, about 15 minutes) is online: open the link from the chat, then use Present. Download it as
  **PowerPoint or PDF** from the deck's menu and carry both on a pen drive, because the CDM hall PC may be offline.
- `Phase_II_Presentation/Speaker_Notes.txt` has what to say on each slide.
- Before the date: fill the [Rank] / [Service No] / [Unit] placeholders on the cover slide. Refresh slide 15 ("The market
  relaxed in June...") with the latest Brent price and the Hormuz status. Rehearse to 15 minutes. Keep the Power BI
  dashboard open to show live if asked.
- Likely questions to prepare for: why deliberate switch-off rather than GPS jamming (slide 11); why 0.69 and not 0.74
  (slide 12, leakage); how the 35-45 days was derived (knee of the shortfall curve); what the Phase 1 proof of
  concept needs (existing establishment, free Sentinel-1 imagery, the pipeline already built).
