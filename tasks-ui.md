# Library UI — useful subset

Working ledger for the Library page. Same spirit as `tasks.md`: a progress
record, not a second product spec. Safe to delete once the work has landed.

The long “professional knowledge-management platform” prompt is mostly a
generic wishlist. This file is the filtered set: only changes backed by data
the Library already has, and only where the current page is actually weak.

Filtering stays client-side on `GET /api/documents`. No backend work in this
pass.

## In

- [x] **Toolbar hierarchy** — primary row (search, source, result count, view,
      sort) then secondary facets. Chips, not a second Clear button.
      [`apps/web/src/pages/DashboardPage.jsx`](apps/web/src/pages/DashboardPage.jsx)
- [x] **Richer sort menu** — Name A→Z / Z→A, recently/oldest added, edition
      newest/oldest, pages, sections, review progress, flagged, health.
      [`apps/web/src/utils/documentFilters.js`](apps/web/src/utils/documentFilters.js)
- [x] **Active-filter chips + Clear all** — search, source, kind, health,
      review, flagged. Removable. No duplicate Clear on the facet row.
- [x] **Hide empty facet groups** — drop zero-count pills; hide Kind / Health /
      Review when there is nothing to choose (e.g. all Unmeasured).
- [x] **Search name + filename + family title** — Library discovery, not
      document-content search. Debounced.
- [x] **`/` focuses search** — same as Triage. Leave ⌘K as the command palette.
- [x] **URL-backed filters and sort** — survive opening a document and coming
      back. `q`, `lane`, `kind`, `health`, `review`, `flagged`, `sort`.
- [x] **Remember sort** in localStorage next to list/cards. Do not persist the
      search box.
- [x] **Show uploaded time** on list rows (and cards) so “Recently added” is
      not a black box.
- [x] **Fix the “% reviewed” click** — it currently filters *in progress*,
      which does not match the label. Toggle fully reviewed documents instead.

## Out

Do not build these. The next prompt should not revive them.

- Advanced Filters popover / drawer
- File type, language, file size, indexed, processing errors, missing metadata
- Date ranges, page-count ranges, section-count ranges
- OCR / parsing status as extra dimensions (Kind and Health already cover this)
- Saved views and user-named views
- Bulk select, tags, collections, reprocess, bulk export / delete
- Column picker / true data table
- Group-by Source / Kind / Year / Review (family grouping stays as it is)
- Server-side pagination, virtualization, or switching Library to
  `GET /api/v2/documents` (v2 cannot express kind / health / review / flagged)
- Persist the search box in localStorage
- New empty states (load / empty corpus / no matches already exist)
- Any change outside Library (Triage, Review, Upload, AppShell chrome)

Already good enough — leave alone:

- Clickable Flagged stat
- List vs Cards + persisted layout
- Family grouping
- Result count `N of M · K families`
- Per-document Native / Scanned / Mixed pills, progress, flags, health
- Sync / Upload actions
- Loading skeletons

## Blocked on backend

Do not fake these in the UI.

| Wanted | Why it cannot ship from the frontend |
|---|---|
| File size sort / filter | Not stored |
| Language | No column |
| Edition date as a real field | `edition_date` exists on the row but is **not** on `DocumentResponse`; Library parses year from the name |
| “Recently updated” | No `updated_at` on the list payload |
| Saved Library views | No table / API (review sessions are findings-queue only) |
| Bulk document actions | Only per-doc delete / export; no tags or collections |
| Server-side faceted pagination | v2 list only has `q`, `status`, `corpus_lane`, sort `name\|newest\|risk` |

## Progress

All **In** items shipped in this pass. Unit tests: `documentFilters`, `sort-proof`,
`libraryState` (148 web tests green). Browser check is the remaining confirmation
that chips, `/`, URL back-navigation, and hidden empty Health actually feel right.
