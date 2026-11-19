# FAQ

**Is this a tool for clinical decisions?** No. It evaluates language models. It is not meant to guide patient care.

**Can a high score justify deployment?** No. It is one screening input. See LIMITATIONS.md.

**Why are results marked provisional?** The 48 items await approval by a qualified reviewer.

**Does it send my data anywhere?** Only the test questions go to the provider you select. Use a local endpoint to avoid that.

**Can we test our own protocols?** Yes. Import a CSV item bank and have a qualified person confirm the key.

**Can it test free-text answers?** Not in version 0.1.

**Why a bootstrap over items?** It shows how much the result depends on which items were chosen, which is the main uncertainty with a small bank.

**Does it work in Krio?** A 20-item Krio subset is included. It is small and reviewed by one speaker.

**Which models are supported?** Gemini, Groq, OpenRouter, and any OpenAI-compatible endpoint. Free-tier model availability changes, so verify ids.

**Who maintains it?** Alhassan Mayei. Issues and suggestions are welcome in the repository.
