# Third-party software

Runtime components use open-source licenses. The dependency lockfiles and each package's distributed license are authoritative; review them before redistribution under your own terms. Model weights are not bundled, and their license is separate from application code.

| Component | License family |
|---|---|
| React, Vite, Tailwind CSS, Radix UI, shadcn/ui patterns, XYFlow, clsx, tailwind-merge, class-variance-authority | MIT |
| FastAPI, Pydantic, SQLAlchemy, Alembic, HTTPX, Uvicorn, argon2-cffi | MIT / BSD |
| pypdf | BSD-3-Clause |
| PostgreSQL | PostgreSQL License |
| Ollama | MIT (model licenses are separate) |
| Lucide icons | ISC |
| Playwright | Apache-2.0 |
| Vitest (development only) | MIT |
| psycopg / psycopg-binary | LGPL-3.0-only; binary distributions also contain third-party notices |

The button/dialog primitives follow the openly licensed shadcn/ui approach using Radix and local source components, adapted for this application.

shadcn/ui MIT notice: Copyright (c) 2023 shadcn.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
