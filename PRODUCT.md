# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Internal operations users (small team, likely the developer and a few staff) at an educational-records service who process Pakistani intermediate/secondary board ("BISE") exam gazette PDFs. They upload official gazette PDFs (80MB+, 4,000+ pages) per board/class/year, then look up individual students' results (roll number, name, marks, board, group, class, year) for verification, support, or reporting. This is an internal admin tool, not a public-facing product — no evidence of a public student-facing search surface exists in the repo.

*Inferred from `AGENTS.md`, `server/boards/*.py` (per-board gazette parsers for Lahore, Faisalabad, Multan, Rawalpindi, Gujranwala, Sargodha, Bahawalpur, Sahiwal, DG Khan), and the two-page app shell (`Upload & Map PDF`, `Search Results`). Not confirmed directly by the user in this session — see note below.*

## Product Purpose

Digitize official BISE exam result gazettes (currently distributed as huge scanned/typeset PDFs with fragile multi-column layouts) into structured, queryable student records in a Postgres database (Supabase), so that a specific student's result can be found by roll number/name/board/class/year in seconds instead of manually scanning a PDF. Success = a gazette PDF uploads without timing out or losing records, and search returns the correct student reliably even under a broad or ambiguous query (name search ranking, trigram indexes, and search timeout fixes are visible in recent commit history).

## Positioning

Purpose-built, per-board PDF layout parsing (`server/boards/*.py`, one module per BISE board with board-specific column/regex handling) plus a pipeline engineered specifically for very large, memory-constrained gazette files (streaming Poppler `pdftotext -layout` page-by-page, chunked Supabase upserts, background job + polling instead of a single long-lived HTTP request). A generic PDF-to-table tool would choke on these files or misread board-specific layouts; this system is tuned to that exact document format.

## Operating Context

- Upload flow: operator selects board / class / year / which optional fields are present in that particular PDF (name, group), submits the PDF, watches a multi-stage progress UI (upload → layout parsing → Supabase sync) driven by polling a background job, since parsing can take minutes on large files.
- Search flow: operator filters by roll number, name, board, class, year, marks range; sees aggregate stats (highest/lowest/average marks, total record count) and a paginated results table.
- Local dev: FastAPI backend on port 8000 (`uvicorn main:app --reload`), Vite frontend (`npm run dev`), both run locally per `AGENTS.md`; Supabase and (in production) Render/Vercel host the deployed pieces.

## Capabilities and Constraints

- Frontend talks to Supabase directly for search/read (`@supabase/supabase-js`), and to the FastAPI backend only for the upload/parse pipeline.
- Upload must handle 80MB+ / 4,000+ page PDFs without loading them fully into memory; parsing runs as a background job polled via `/api/upload-status/{job_id}`, not a blocking request.
- Search ranking and count queries run through a Postgres RPC (`search_students`) with a count cap (`COUNT_CAP` = 200,000) and trigram indexes, to keep broad/common-name searches from timing out.
- 10 Punjab/Federal boards currently supported in the UI's board list; per-board parsing logic lives server-side in `server/boards/`.
- No authentication/authorization layer is visible in the current frontend code — treated here as an existing constraint/fact to preserve as-is, not something this redesign should add or remove.

## Evidence on Hand

- Real per-board parser modules for 9+ boards (`server/boards/`) confirm which boards are actually supported today.
- A sample gazette PDF exists at `server/temp_uploads/BISE-Sahiwal-Class-10-Gazette.pdf` and an untracked `multan.pdf` at the repo root, usable as realistic reference content for empty/loading/error states, but not to be treated as design assets.
- No logo, brand guideline, marketing copy, or named product identity beyond the UI's current self-label "BISE Gazette Admin" was found. No customer testimonials, pricing, or public-facing claims exist — none should be invented.

## Product Principles

- Correctness and reliability of large-file processing and search outrank visual flourish — this is an internal operations tool, not a marketing surface.
- Preserve all existing state/data-fetching logic, Supabase RPC contracts, upload/polling behavior, and functional field names exactly; this redesign changes presentation, not behavior or data shape.
- Keep board-specific and record-specific terminology (roll number, gazette, board, group, class, marks) as-is — these are domain terms operators already know, not copy to be softened.
- Design for two square-in-front-of-the-screen internal workflows (upload a gazette; search records) rather than for a broad, unfamiliar audience.

## Accessibility & Inclusion

No product-specific accessibility requirement was established by the user this session; standard web accessibility practice (contrast, focus states, keyboard operability of forms/tables/pagination) applies as a baseline since this is a tool operators use daily.

---

**Note on this file's provenance:** this session's product-truth interview (`AskUserQuestion`) was declined by the user, who then re-issued the original "redesign this app, do it locally" instruction after installing this design skill — read as "proceed without further questions." Everything above was therefore inferred from the repository (code, `AGENTS.md`, recent git history) rather than confirmed live; it is offered as a working record, not a locked contract. Correct anything here that's wrong whenever it becomes relevant.
