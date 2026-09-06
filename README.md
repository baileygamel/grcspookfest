# Avatar Picker

Five-step flow: **character → look → username → city → share**. Data-driven, so
adding a base character or a tour stop is config plus one command — no code changes.

```
index.html      the picker
styles.css      brand tokens (cyan / magenta / orange, Merriweather + Mulish), dark + light
app.js          step flow, validation, share-card canvas, persistence, embed API
events.js       GRC Barcade tour stops — hand-edit this one
characters.js   GENERATED manifest — do not hand-edit
assets/<id>/    GENERATED per-variant PNGs (NN.png for tiles, NN@2x.png for the preview)
tools/          the sheet pipeline
```

## Running it

Because the pages load `characters.js` and the PNGs, open it over HTTP rather
than double-clicking the file:

```bash
cd /Users/bailey/Desktop/avatar-picker && python3 -m http.server 8780
```

then visit <http://localhost:8780>. (Serving from `~/Desktop` needs the terminal
app to have Files-and-Folders access to Desktop in System Settings → Privacy.)

## Adding a base character

One contact sheet = one base character. Every cell on it is a variant of that
same character.

1. Drop the sheet in `tools/sheets/src/` — `.svg` (the background-removed export)
   or `.png`.
2. Add `tools/sheets/<id>.json`:

   ```json
   {
     "id": "char-04",
     "name": "Name shown on the landing page",
     "tagline": "Optional one-liner",
     "src": "tools/sheets/src/char-04.svg",
     "cols": 6,
     "rows": 4,
     "default": 3
   }
   ```

3. Run it:

   ```bash
   python3 tools/slice_sheet.py
   ```

That writes `assets/char-04/01.png …` and rebuilds `characters.js`.

### Optional config keys

| key        | what it does |
|------------|--------------|
| `variants` | Captions under each tile, in reading order. Absent (the default) → tiles are picked by eye and stay caption-free. Don't put skin-tone descriptors here — char-01's sheet has them baked in, and they're parked under `sourceLabels`, which the pipeline ignores. |
| `labels`   | `true` when the sheet has caption pills baked under each bust (like char-01). They get detected and trimmed off. |
| `grid`     | `{"x0","y0","cellW","cellH"}` when the grid doesn't start at 0,0 or isn't exactly `size / cols`. char-03's grid starts 60px down. |
| `erase`    | Rectangles `[x0,y0,x1,y1]` to blank before slicing — for non-avatar furniture, like the stray wordmark sitting in the corner of char-03's sheet. |
| `skip`     | `[[row, col], …]` cells that aren't avatars. |
| `default`  | 1-based variant used as the character's thumbnail. |

### What the pipeline handles

The sheets arrive in three different states and `slice_sheet.py` copes with all:

- **`.svg`** — not actually vector. The design tool wraps the original raster
  plus a luminance mask, so `svg_to_rgba.py` unwraps them back into real RGBA.
- **`.png` with alpha** — used as-is.
- **`.png` without alpha** — the image generator paints a *fake* checkerboard
  instead of being transparent. That gets flood-filled away from the border.
  This is a fallback: it can't reach background sealed behind hair strands, so
  those cells keep white pockets. Prefer a properly background-removed source.

Every variant is cropped to one shared frame anchored on the hair line, so faces
land in the same place across a character's whole set.

## Tour stops

`events.js` holds the cities. Each entry:

```js
{
  id: "denver",              // stable key, used in the saved selection
  city: "Denver",
  area: "Bellevue",          // optional, shown as "Bellevue area"
  date: "2026-10-21",        // ISO, for anything downstream
  dateLabel: "Wed, Oct 21",  // what people actually see
  venue: "Lone Tree Brewing Company",
  url: ""                    // optional registration link — see below
}
```

Add, remove or reorder freely; the city step renders whatever is in the array.

## Sharing

Step 5 draws a 1080x1080 card on a canvas — avatar, username, the character
badge, "I'm going to the GRC Barcade", city, date and venue — and offers the
caption in an editable box.

Worth knowing about the two networks, because neither does what you'd hope:

- **LinkedIn** removed prefilled text from `share-offsite` years ago. So the
  button copies the caption, downloads the image, *then* opens the composer —
  the person pastes and attaches. If you fill in an event `url`, it uses the
  proper `share-offsite` link with that URL instead.
- **Instagram has no web composer at all.** Nothing can post to it from a
  browser. On a phone the button hands the image and caption to the OS share
  sheet (where Instagram appears); on desktop it downloads the image and copies
  the caption, and says so.

The canvas has to read the avatar PNGs, so **serve over HTTP** — opening
`index.html` off the filesystem taints the canvas and the download silently fails.

## About sharpness

Each contact sheet is 1536x1024, so a single avatar is only ~190-240 real pixels
wide. On a 2x display that is the hard ceiling on detail: blow one up past life
size and it goes soft, because there is nothing more to show.

So the picker never displays art past life size. Tiles are ~120-150 CSS px, and
the step-3 preview is capped from the manifest's 1x `frame` width. The preview
is the one place big enough to need real device pixels, so it loads `NN@2x.png`
— a Lanczos upscale with a light unsharp pass, which reads noticeably crisper
than letting the browser do the same job bilinearly.

**If you want it genuinely sharper, that has to come from the source.** Generate
the sheets at 3072x2048 or larger and everything downstream doubles for free;
nothing in the pipeline is hard-coded to 1536x1024.

## Embedding

```html
<script>window.AvatarPicker = { onComplete: function (sel) { console.log(sel); } };</script>
<script src="characters.js"></script>
<script src="app.js"></script>
```

`onComplete` fires on confirm with:

```js
{
  characterId, characterName,
  variantIndex, variantName, image, image2x,
  username,
  eventId, eventCity, eventDate, eventVenue
}
```

It fires when the share step is reached — that's the point where every choice is
made.

`AvatarPicker.getSelection()` returns the same shape at any time, or `null`.
The last confirmed choice is kept in `localStorage` under
`avatar-picker:selection` and restored on load.
