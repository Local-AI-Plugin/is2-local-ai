# RAG source documents

These are reference copies of the documents in the RAG corpus. The pipeline doesn't read from this folder: ingest reads `software/rag/data/documents/`, which is gitignored. To rebuild the corpus, copy these PDFs there and run `rag ingest` (see [software/rag/README.md](../../software/rag/README.md)).

All five are US government publications that are published openly. The three Army publications say "Approved for public release; distribution is unlimited."

| File | Document | Edition | Publisher |
|---|---|---|---|
| `ADP 5-0 The Operations Process.pdf` | ADP 5-0, *The Operations Process* | 31 July 2019 (supersedes ADP 5-0 and ADRP 5-0, 17 May 2012) | Headquarters, Department of the Army |
| `FM 5-0 Planning and Orders Production.pdf` | FM 5-0, *Planning and Orders Production* | 16 May 2022 | Headquarters, Department of the Army |
| `FM 3-98 - Reconaissance and Security Operations.pdf` | FM 3-98, *Reconnaissance and Security Operations* | 10 January 2023 (supersedes FM 3-98, 1 July 2015) | Headquarters, Department of the Army |
| `DoD_Dictionary_of_Military_Terms.pdf` | JP 1-02, *Department of Defense Dictionary of Military and Associated Terms* | 12 April 2001, as amended through 9 June 2004 | Joint Staff |
| `DoD_Terminology.pdf` | *DOD Dictionary of Military and Associated Terms* | As of September 2018 | Joint Staff, J-7 |

The Army publications are available from the Army Publishing Directorate (https://armypubs.army.mil/). The Joint Staff publishes the DoD Dictionary at https://www.jcs.mil/Doctrine/DOD-Terminology-Program/.

## Notes for RAG testing

- **The two dictionaries are different editions.** Some definitions changed between 2004 and 2018, for example "commander's intent" and "decisive point." Some terms, such as "center of gravity" and "battle rhythm," are only in the 2018 edition. A good answer should prefer the 2018 definition or say that the editions differ.
- **Some front matter doesn't extract.** The title pages of ADP 5-0 and FM 5-0 use a font that turns into nonsense characters when extracted as text (for example `0D\ 2022` for "May 2022"). Questions about their titles or dates may fail because of extraction, not retrieval.
- **The 2004 acronym list is two columns.** Text extraction can interleave the columns, so an acronym's line can contain the expansion of a neighbouring acronym.
- File names are kept identical to `data/documents/`, including the "Reconaissance" typo, so the two sets match.
