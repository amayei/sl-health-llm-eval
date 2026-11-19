# FAQ

**Is this a tool for clinical decisions?** No. It evaluates language models. It is not meant to guide patient care.

**Can a high score justify deployment?** No. It is one screening input. See LIMITATIONS.md.

**Why are some results marked provisional?** Runs that include unapproved (draft) items carry that label. The built-in 48 items are approved by their author, without independent review.

**Does it send my data anywhere?** Only the test questions go to the provider you select. Use a local endpoint to avoid that.

**Can we test our own protocols?** Yes. Import a CSV item bank and have a qualified person confirm the key.

**Can it test free-text answers?** Not in version 0.1.

**Why a bootstrap over items?** It shows how much the result depends on which items were chosen, which is the main uncertainty with a small bank.

**Does it work in Krio?** A 20-item Krio subset is included. It is small and reviewed by one speaker.

**Which models are supported?** Gemini, OpenAI (ChatGPT family), Anthropic (Claude family), Groq, OpenRouter, and any OpenAI-compatible endpoint. Model availability changes, so verify ids with the list-models workflow. See the user guide for how ChatGPT and Claude are included.

**Who maintains it?** Alhassan Mayei. Issues and suggestions are welcome in the repository.
