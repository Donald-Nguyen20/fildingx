# -*- coding: utf-8 -*-
"""Read-only logic lookup over the Toshiba DCS engineering databases.

These are the CAD databases the plant's control logic was actually designed in
-- one SQLite file per controller, ~21 of them for Unit 1 -- as opposed to the
logic-diagram PDFs indexed in the document library. The PDFs carry the same
sheets, but text extraction throws away the geometry that said which gate feeds
which, so they can answer "does this signal exist" and not "what trips it".
These files answer the second question, which is the one worth asking.

Copied verbatim from T_Designer_Lite/core so the engine stays a drop-in: the
modules import each other by relative name and read their macro tables from
this directory, so they behave the same here as they do there. Only the package
header is ours. Keeping the sources untouched means a fix upstream can be
re-copied rather than re-merged.

What was deliberately left behind: the Qt UI, the sheet renderer's symbol
geometry, the simulators, and importer.py -- which is why this __init__ does not
mirror the original's. importer.py reads DEF text and PDFs and pulls in PyMuPDF
and pdfplumber to do it; nothing in a logic lookup needs either, and importing
it here would make this package fail to load wherever those are absent.

Entry points, in the order a lookup normally uses them:

    project_index.find(name)            locate a signal across every controller
    cond_tree.formula(db, sheet, net)   one-line cause, e.g. "AND( a, /b )"
    cond_tree.build(...)                the full condition tree behind a signal
    cond_tree.blockers(tree, env)       of those conditions, which are unmet
    signal_graph.trace_project(...)     the graph, across sheets and controllers

Two departures from the original, both about not writing to the plant's data:

    - dbreader.connect() opened the file read-write. Every caller here only
      reads, and these are the design masters, so the connection now says so --
      file:...?mode=ro, the way db_query.py opens the document library. The
      other two places that opened a source DB directly, project_index.build()
      and ce_matrix, go through the same dbreader.ro_uri().
    - project_index writes its index beside whatever index_path() resolves to,
      which is ~/.tdesigner_index.db -- shared with T_Designer_Lite itself, so
      the two would evict each other and rebuild on every switch. Callers here
      pass out_path= instead; logic_query.py names it after a hash of the DCS
      folder and keeps it in APP_DIR, one index per unit.

Everything else is left as it came, so that this copy stays a copy.
"""

from . import cond_tree, dbreader, project_index, signal_graph  # noqa: F401

__all__ = ["cond_tree", "dbreader", "project_index", "signal_graph"]
