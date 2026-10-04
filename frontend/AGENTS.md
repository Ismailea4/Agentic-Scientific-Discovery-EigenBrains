<!-- LOVABLE:BEGIN -->
> [!IMPORTANT]
> This project is connected to [Lovable](https://lovable.dev). Avoid rewriting
> published git history — force pushing, or rebasing/amending/squashing commits
> that are already pushed — as it rewrites history on Lovable's side and the
> user will likely lose their project history.
>
> Commits you push to the connected branch sync back to Lovable and show up in
> the editor, so keep the branch in a working state.
<!-- LOVABLE:END -->

- Keep Noesis as a frontend-only TanStack Start shell over the repository's unchanged same-origin `/api` and `/health` contracts, because the Databricks Omnigent backend integration remains externally owned.
- Read discovery-lab data only through the read-only feed (`discolab/bridge.py`: `/lab/sources|state|activity|experiment|stream`) via the `/lab-proxy/$` relay route, because the feed sends no CORS headers and its contract is owned by the backend team; mirror its shapes in `src/noesis/api/lab-types.ts`.
- Show live/recorded lab data when the feed is connected and a source is picked, and labelled SAMPLE fixtures otherwise, so evidence labels stay honest.
