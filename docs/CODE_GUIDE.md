# Safarnama Code Guide

This guide explains every file in the project: what it does, how it does it, and why it was built that way. Read it alongside the code. Each section matches one file.

## 1. The big picture

A user sends five things: origin, destination, dates, budget and number of travellers. Safarnama returns a day by day itinerary with transport, a hotel, places to visit and the total cost.

Inside, seven agents share one object called the **state**. Each agent reads what it needs from the state and writes back only its own part. LangGraph decides which agent runs next.

```
request
  -> Coordinator         splits the budget into envelopes
  -> Transport, Stay, Places   run at the same time, each inside its envelope
  -> Budget check        adds up the real cost
       over budget? -> back to Coordinator (max 3 rounds)
  -> Writer              builds the day by day schedule
  -> Critic              checks the schedule against hard rules
       problem found? -> back to the agent responsible (max 2 rounds)
  -> final plan
```

Around the agents sits the product: an animated splash page, accounts with email and password, a dashboard with the trip form, and an itinerary the user can edit and regenerate or download as a PDF.

Four ideas run through the whole codebase:

1. **The LLM chooses, code checks.** The model only picks from options that code has already filtered. Every answer is validated. If the model fails or is switched off, a rule based pick is used instead.
2. **Money is integer rupees.** No floats, so no rounding errors.
3. **Every data source can fail safely.** Real APIs fall back to sample data and the error is recorded.
4. **The user's choices win.** When the user picks a hotel, a journey or a place, it is pinned. The agents plan everything else around it.

### How editing and regenerating works

The plan the API returns includes `options`: every outbound journey, return journey, hotel and place the agents considered. The frontend shows these as choices. When the user swaps or removes something, the frontend sends the same trip again with extra fields:

| Field | Meaning |
|---|---|
| `outbound_id`, `return_id` | Use these journeys |
| `stay_id` | Use this hotel |
| `include_places` | Always visit these |
| `exclude_places` | Never visit these |
| `note` | Free text the AI agents read, such as "a quieter hotel" |

Each agent checks for these first. A pinned choice also sets that agent's floor, so the coordinator never tries to cut below what the user chose and takes money from the other agents instead.

## 2. One trip, step by step

This is a real run from the project with the LLM switched off.

**Request:** Indore to Goa, 20 to 23 November 2026 (3 nights, 4 days), 2 travellers, budget Rs 12,100.

| Step | Agent | What happened |
|---|---|---|
| 1 | coordinator | Split Rs 12,100. Food needs at least Rs 500 x 2 people x 4 days = Rs 4,000, more than the normal 15 percent, so food was raised and activities and the other envelopes were trimmed. Transport and stay each got Rs 4,050 |
| 2 | places, stay, transport | Ran in parallel. Stay picked Zostel Anjuna (Rs 900 a night, Rs 2,700 total). Transport found the cheapest valid return pair is Rs 5,800, more than its Rs 4,050 envelope, so it took the cheapest and noted it |
| 3 | budget_check | Total Rs 12,500, over by Rs 400 |
| 4 | coordinator | Round 1. Transport is already at its cheapest, so it cut Rs 400 from stay, the agent with room to spend less |
| 5 | stay | Reran with a lower cap and picked Baga Beach Hostel (Rs 750 a night, Rs 2,250 total) |
| 6 | budget_check | Total Rs 12,050, within budget |
| 7 | writer | Built 4 days with 6 places |
| 8 | critic | Found one day with too much local travel and sent it to the places agent with the hint "nearby" |
| 9 | places, budget_check, writer | Places reran keeping only spots within 30 km, the cost was rechecked and the schedule rebuilt with 5 places |
| 10 | critic | No issues. Done |

Every row above is a trace event, so the same story can be shown live in the frontend.

## 3. Folder map

```
app/                    the application
  state.py              data models and the shared state
  graph.py              connects the agents with LangGraph
  llm.py                calls the model and validates its answer
  auth.py               accounts, passwords, sessions, admin check
  trips.py              saved itineraries
  admin.py              admin search, ban, delete and itinerary list
  pdf.py                builds the itinerary PDF
  api.py                FastAPI web endpoints
  agents/               one file per agent
  rag/                  retrieval: vector index, travel guide, traveller memory
  ml/                   Safarnama's own chat model: entity tagging, seed sentences, intent model
  profile.py            the 14 travel interests and each user's picks
  db.py                 one SQLite file for profiles, memory, training examples and learned words
  providers/            where data comes from
  tools/                plain Python helpers: budget maths, distance, checks
fixtures/               sample data for 8 routes
evals/                  50 test trips and the comparison runner
tests/                  160 automated tests, 99 percent coverage
frontend/               Next.js web app
docs/                   this guide and the README screenshot
.github/workflows/      the CI pipeline
```

## 4. Core files

### app/state.py

Defines every data shape in the project with Pydantic. Pydantic checks types and rules automatically, so bad data is rejected the moment it is created.

| Model | What it holds |
|---|---|
| `TripRequest` | The user's input. Cleans city names (" goa " becomes "Goa"), rejects same origin and destination, rejects an end date before the start date, caps trips at 14 nights. Gives `nights`, `days` and `trip_dates()`. Also carries the user's pinned choices and note (see "How editing and regenerating works") |
| `BudgetPlan` | The five envelopes: transport, stay, food, activities, buffer. `total` adds them up |
| `TransportOption` | One journey: mode, operator, departure and arrival times, total price for all travellers, whether it is overnight. `hours` gives the duration |
| `StayOption` | One hotel: price per room per night, rating, location, check-in desk timings, whether it has a 24 hour desk |
| `PlaceOption` | One attraction: entry fee per person, hours needed, opening times, weekly closed days, location, rating |
| `PlanItem` | One line in a day's schedule: start, end, title and type (travel, checkin, place, free) |
| `DayPlan` | One day: date, weekday, list of items, km of local travel |
| `CriticIssue` | One problem the critic found, which agent should fix it, and the day it is about when there is one |
| `TraceEvent` | One agent run: name, start time, duration, tokens, cost, short note |
| `TripState` | The shared object every agent works on |

**Fields in TripState worth knowing:**

- `round` counts budget negotiation rounds. `critic_round` counts critic rounds.
- `rerun` is the list of agents the coordinator wants to run next.
- `instructions` holds hints per agent, for example `{"stay": ["cheaper", "late_checkin"]}`.
- `floors` is the cheapest possible spend per category, which agents report so the coordinator knows how far each can go down.
- `outbound_options`, `return_options`, `stay_options`, `place_options` keep every option the agents saw, so the user can pick a different one.
- `trace`, `errors`, `notes` and `floors` use **reducers** (`Annotated[..., add]` and `merge`). Three agents run at once, and without a reducer LangGraph would not know how to combine their writes to the same field. With it, lists are appended and dicts are merged.
- `writer_notes` and `critic_notes` have **no** reducer on purpose. The writer and critic can run two or three times in one plan. Each run replaces its old notes, so the user never sees a stale note about a schedule that has since changed. `all_notes()` joins all three lists without repeats.

### app/graph.py

Wires the agents together.

- `build_graph()` adds the seven nodes and the edges between them.
- `after_coordinator` returns the `rerun` list, so only the agents that need to change run again. Returning a list makes them run in parallel. An empty list goes to the writer.
- `after_budget` goes back to the coordinator if the plan is over budget and fewer than 3 rounds have run, otherwise to the writer.
- `after_critic` ends if there are no issues or 2 critic rounds have run. Otherwise it sends the work to the responsible data agents. If only the writer is responsible, the writer runs again.
- Transport, stay and places each have their own edge to budget check. This matters: if only stay reruns, budget check runs straight after it without waiting for the others.
- `plan_trip()` runs the whole graph and returns the final state. It calls `split_budget` first so an impossible budget fails fast with a clear error.
- `stream_trip()` yields each step as it happens, used by the live endpoint.
- `recursion_limit` of 60 is a safety cap on total steps.

### app/llm.py

The only place the model is called.

- `enabled()` is true only when `ANTHROPIC_API_KEY` is set and `LLM_MODE` is not `off`.
- `ask_json(system, prompt, schema, usage)` sends the prompt with the JSON schema attached, pulls the JSON out of the reply, and validates it against the Pydantic schema. If validation fails it retries once and tells the model what was wrong. If it still fails, or the API errors, it returns `None`, and every agent treats `None` as "use the rule based pick".
- `Usage` collects tokens and estimated cost. Prices per million tokens come from environment variables so you can set your model's real rates.

### app/auth.py

Accounts with an email and password, stored in the `users` table.

**Signing up** (`sign_up`): the body is checked first. The email is cleaned and lower cased, the name has extra spaces removed, the date of birth must be real and at least 13 years ago, and the password needs 8 or more characters with a letter and a number. An email that already has an account gets 409. The new user gets a random **5 digit ID** from 10000 to 99999 (`new_id` retries until it finds a free one), and becomes an admin if the email is in `ADMIN_EMAILS`.

**Passwords** are never stored. `hash_password` makes a random 16 byte salt and runs PBKDF2 with SHA-256 for 200,000 rounds, saving `pbkdf2_sha256$rounds$salt$hash`. `password_matches` repeats that with the saved salt and compares with `hmac.compare_digest`, which takes the same time however much of the guess was right.

**Signing in** (`sign_in`): an unknown email and a wrong password give the same message, so nobody can test which emails have accounts. Wrong tries are counted per email and visitor address in `app/limits.py`, and unknown emails count the same way, so the replies never show which emails exist. The message says how many tries are left near the end, and the 5th wrong try blocks that email from that address for 15 minutes (429). Someone at another address can still sign in, so a stranger cannot lock you out. A banned account only hears that it is banned after the right password (403). A right password clears the counter and records the time. The API also allows each address 30 sign in, sign up and reset requests per 15 minutes.

**Forgot password** (`start_reset`, then `forgot_password`): the first step emails a random 6 digit code through `app/mailer.py` and stores only a keyed hash of it. The reply is the same whether or not the email has an account, and each email can ask for 3 codes per 15 minutes. The second step needs that code, which expires after 15 minutes and stops working after 5 wrong tries. Without `SMTP_HOST` the code is written to the API log, which suits local use only.

**Sessions**: the token is set as an httpOnly, SameSite=Lax cookie, so page scripts cannot read it. When the cookie is used for a request that changes data, the request must also carry `X-Requested-With: safarnama`, which a form on another site cannot send. API clients and tests can still send `Authorization: Bearer`. The API refuses to start without a `SECRET_KEY` of at least 32 characters, unless `SAFARNAMA_ENV` is `dev` or `test`.

**Change password** (`change_password`) needs the current password.

**Sessions:** `make_token` signs a JWT with the user ID, a token version and an expiry 7 days ahead. `current_account` decodes it, loads the user and refuses the token if the user is gone, banned, or the version has changed. Changing or resetting a password and being banned all raise the version, so every old session stops working at once. `current_user` gives just the email, which the planner, memory and profile code use as their key. `admin_account` adds a 403 for anyone who is not an admin.

### app/trips.py

Every plan the backend returns is saved to `itineraries` with its route, dates, travellers, budget, total and the full plan as JSON, and the response gets a `trip_id`. Sending that `trip_id` back when regenerating or chatting updates the same itinerary instead of making a new one, but only if it belongs to the same user. `trips_for`, `get_trip` and `delete_trip` power the My itineraries list.

### app/admin.py

- `search_users` finds users by a user ID (with or without #, matching from the start, so 395 finds 39562), or by part of a name or email, and counts their itineraries.
- `user_detail` returns one user and their itineraries.
- `set_banned` bans or unbans and raises the token version, so a banned user is signed out right away.
- `delete_user` removes the account and everything tied to it: itineraries, interests, memory and chat turns. Training examples stay, since they hold no personal details.
- `all_trips` lists every itinerary with the creator's name, searchable by user ID, itinerary ID, city or name.
- `stats` counts users, banned users and itineraries.

The API stops an admin from banning or deleting their own account. `scripts/make_admin.py` turns an existing account into an admin from the command line.

### app/pdf.py

Builds the downloadable itinerary with ReportLab.

- `PlanDoc` is a Pydantic model of exactly the parts of the plan the PDF needs. The frontend sends back the plan JSON it received, and anything extra is ignored. The JSON key `return` is a Python keyword, so the field is `return_` with an alias.
- `build_pdf` lays out: the name, route and dates; a cost table; travel and stay with times and prices; one block per day; notes; and a short disclaimer. Each day is wrapped in `KeepTogether`, so a day is never split across two pages.
- Uses "Rs" instead of the rupee sign, because the built in PDF fonts do not have that symbol. Embedding a font file would fix it, at the cost of a larger repo.
- `filename` gives names like `safarnama-delhi-jaipur-2026-11-27.pdf`.

### app/api.py

The FastAPI web server.

| Endpoint | Sign in | What it does |
|---|---|---|
| `GET /` | no | Redirects to the docs page |
| `GET /health` | no | Says the server is up and whether the LLM is on |
| `GET /routes` | no | Lists routes in the sample data |
| `POST /auth/signup`, `/auth/login`, `/auth/logout`, `/auth/forgot/start`, `/auth/forgot` | no | Create an account, sign in, sign out, get a reset code, reset a forgotten password |
| `POST /auth/change-password` | yes | Change password, signs out other devices |
| `GET /trips`, `GET` and `DELETE /trips/{id}` | yes | Saved itineraries |
| `/admin/...` | admin | Stats, user search, user detail, ban, delete, all itineraries |
| `GET /auth/me` | yes | Returns the signed in email. The frontend uses it to check a saved session is still valid |
| `POST /plan` | yes | Takes a `TripRequest` and returns the full plan |
| `POST /plan/stream` | yes | Server sent events. Sends one message per agent step, then a final message with the full plan |
| `POST /plan/pdf` | yes | Takes a plan and returns the PDF as a download |
| `POST /plan/text` | yes | Takes free text, turns it into a request with the intake agent, then plans. Needs an API key |

- `to_response()` turns the state into clean JSON. It includes `options`, each list sorted by price, so the frontend can offer swaps.
- A budget too low for food returns HTTP 422 with a clear message instead of crashing.
- CORS allows the addresses in `CORS_ORIGINS`, by default the Next.js dev server.

## 5. Agents (app/agents/)

### common.py

- `traced(name)` is a decorator that wraps every agent. It times the run, gives the agent a `Usage` object for token counting, and adds a `TraceEvent` to the state. Agents can return a `_note` key, which becomes the short note in the trace.
- `money(n)` formats rupees, for example `Rs 12,050`.
- `user_note(state)` adds the user's free text note to every LLM prompt, so all agents see it.

### coordinator.py (Coordinator and Budget check)

The coordinator controls the money.

**First run** (no budget plan yet): calls `split_budget` and asks all three data agents to run. If the user wrote a note but no LLM is connected, it adds a note saying so, rather than silently ignoring it.

**Later runs** (plan is over budget): decides who has to spend less.

1. It first asks the LLM for new envelopes, if enabled. `valid_reallocation` rejects the answer if any envelope is below that category's cheapest possible spend, or if the total exceeds the budget.
2. Otherwise `rule_based_cuts` works out each agent's "room": what it spent minus the cheapest it could spend. It takes the overspend from the agent with the most room first, then the next.
3. Agents whose envelope dropped below their spend get the hint `cheaper` and go on the `rerun` list. The round counter goes up.
4. If nobody has room left, `stuck` adds one note, "could not fit the budget, still over by Rs X", and the graph moves on to the writer. It never loops forever.

`add_hint` adds a hint without duplicates and without changing the old dict, which is safer with shared state.

**budget_check** is a separate node in the same file. It calls `compute_totals` and writes the breakdown, total and overspend. No LLM.

### transport.py

1. Searches outbound journeys that **arrive on** the start date and return journeys that **depart on** the end date.
2. Builds every outbound and return pair, keeping only pairs where the return leaves at least 4 hours after arrival. This matters for day trips.
3. Records the cheapest pair price as its floor.
4. Keeps pairs within the transport envelope and ranks them with `score`: price as a share of the envelope, plus 0.05 for each daytime hour spent travelling. Overnight journeys count as zero daytime hours, because you sleep on them.
5. With the hint `cheaper`, ranks by price only.
6. Sends the top 6 to the LLM, which returns an index. The index is checked to be in range before use.
7. If nothing fits the envelope, it takes the cheapest pair and says so in the note. The coordinator then handles the overspend.

**User choices:** if `outbound_id` or `return_id` is set, only pairs using those journeys are kept, whatever they cost, and the floor becomes their price. If the chosen journey does not work with the dates, for example the return would leave before arrival, it picks another and adds a note explaining why.

### stay.py

1. Day trips return no hotel and a floor of zero.
2. Works out the cap per room per night: stay envelope divided by nights times rooms. Rooms are two people each.
3. With the hint `late_checkin`, which comes from the critic, it keeps only hotels whose desk is open when the traveller arrives, or that have a 24 hour desk. `can_check_in` does this check using the arrival date, so an arrival at 00:15 counts as late.
4. Ranks hotels within the cap by rating, or by price with the hint `cheaper`.
5. Sends the top 5 to the LLM, which returns a hotel id. Only ids from the list are accepted.
6. If nothing fits, it takes the cheapest and notes it.

**User choices:** if `stay_id` is set and that hotel exists, it is returned straight away with its full cost as the floor. This happens before the `late_checkin` and `cheaper` hints are looked at, so neither the critic nor the coordinator can swap out a hotel the user chose. If the critic finds a problem with it, that problem is shown to the user as a note. If the hotel id is unknown, another is picked with a note.

### places.py

1. Removes places closed on every day of the trip.
2. With `cheaper`, keeps only free places. With `nearby`, which comes from the critic, keeps only places within 30 km of the hotel.
3. Sorts by rating, with a boost of 0.4 for categories in the user's preferences.
4. Greedily adds places while both the activities budget (entry fee times travellers) and the available hours still fit. Available hours are 3 on arrival and departure days and 7 on full days.
5. The LLM may propose a set of place ids. Unknown and duplicate ids are dropped, and the set is accepted only if code confirms it fits the money and the time.

**User choices:** places in `exclude_places` are removed before anything else. Places in `include_places` are always chosen first, unless they are closed on every trip day, which gets a note. Their entry fees become the floor, and they are kept even with the `cheaper` or `nearby` hints. Their cost is measured on its own: the budget check for other places uses whichever is larger, the activities envelope or the cost of the added places. Without this, one expensive place the user added would use up the whole envelope and block even free places, which was a real bug found while testing.

### writer.py

Turns the chosen transport, hotel and places into a timetable. It is fully deterministic. The LLM only writes a short summary at the end.

- `day_window` works out when each day starts and ends. Normal days run 09:00 to 20:30. On arrival day the start moves to arrival plus 45 minutes of transfer plus 30 minutes to check in. On departure day the end moves to 2 hours before the return journey.
- `schedule_day` fills a day using **nearest place first**: from the current location, it picks the closest place that is open that weekday, can start after travelling there, finishes before closing time and before the day ends, and stays within the day's hour limit. It repeats until nothing fits. Travel time between places assumes 25 km/h in city traffic.
- Places with weekly closed days are scheduled first, since they have fewer possible days.
- `target` spreads hours evenly, so one day is not packed while another is empty. A full day with nothing that fits is shown as "Free day".
- **Day trips.** `plan_day_trips` finds places more than 2 hours from the hotel and gives each one its own full day (never arrival or departure day). On that day `schedule_day` tries the far place first, leaving at 06:30 instead of 09:00, then fills the rest of the day as usual. Without this, a place like Dudhsagar Falls, 5 hours of activity and over 2 hours away, could never be reached before it closes and was always dropped.
- `try_fit` is the shared check: can this place start after travelling there, finish before it closes and before the day ends, on a day it is open.
- Places that fit no day are dropped with a note, and the cost is recomputed. Its notes go into `writer_notes`, which each run replaces.

### critic.py

1. Runs every hard check from `tools/checks.py`. These are rules, not opinions, so they are never left to the model.
2. Converts issue types into hints: `late_arrival` gives stay the hint `late_checkin`, and `too_much_travel` gives places the hint `nearby`.
3. If there are no hard issues, the LLM may add up to 3 soft tips. These only become notes and never trigger reruns.
4. After the last allowed round, unresolved issues become notes so the user sees them.
5. `user_trips`: if a day has too much travel only because of a place the user added, that is the user's choice, not a mistake. It becomes a friendly note, "Wed 18 Nov is a long day out, about 132 km in total, for Dudhsagar Falls Jeep Safari", and is not sent back to the places agent, which would otherwise try to remove it.
6. Its notes go into `critic_notes`, which each run replaces.

### intake.py

Used only by `/plan/text`. Turns a sentence like "3 days in Goa from Indore next Friday, 15k, 2 people" into a `TripRequest`. Today's date is passed in so "next Friday" can be resolved. The result goes through the same validation as the form. Without an API key it raises a clear error.

## 6. Providers (app/providers/)

### base.py

Three abstract interfaces: `TransportProvider`, `StayProvider`, `PlacesProvider`. Agents only know these interfaces, never a specific data source. `ProviderError` is the single error type every provider raises.

`direction` for transport is either `arrive_on` (outbound: arrive on this date) or `depart_on` (return: leave on this date).

### fixture.py

Reads the sample JSON in `fixtures/` and turns it into typed options.

- Files are read once and cached with `lru_cache`.
- The same timetable is used in both directions of a route.
- Overnight outbound journeys are dated the evening before, so they arrive on the trip's start date.
- Prices in the file are per person and are multiplied by the number of travellers.
- `supported_routes()` lists available routes for the API and evals.

### serpapi.py

Live data from SerpApi's Google Flights and Google Hotels engines.

- `call` sends the request with a 15 second timeout and turns any network or API error into a `ProviderError`.
- `IATA` maps city names to airport codes.
- `parse_clock` turns times like "3:00 PM" into a time value.
- Results are mapped onto the same models as the sample data, so agents cannot tell the difference.

### __init__.py

- `WithFallback(primary, backup)` tries the live provider and switches to fixtures on `ProviderError`, recording why in `last_error`. Agents copy that into `errors` and tell the user that sample data was used.
- `get_providers()` reads `PROVIDER_MODE`. `fixture` (the default) uses sample data. `live` uses SerpApi for flights and hotels, each wrapped with a fixture fallback. Places always use fixtures.

## 7. Tools (app/tools/)

### budget.py

- `split_budget(req)` creates the envelopes:
  1. Starts at transport 35, stay 35, food 15, activities 10 percent, using integer division.
  2. Day trips move the stay share into activities.
  3. If food is below Rs 500 per person per day, food is raised to that floor and the difference comes out of activities first.
  4. Buffer gets whatever is left, so the five envelopes always add up exactly to the budget.
  5. If buffer would go negative, the shortfall is taken from transport and stay.
  6. If the budget cannot cover food alone, it raises `BudgetTooLowError` with the minimum needed.
- `rooms_needed` assumes two people per room.
- `compute_totals(state)` adds transport, stay (price per night times nights times rooms), activities (entry fees times travellers) and food. The buffer is a reserve and is not counted as spent. Overspend is never negative.

### geo.py

- `km_between` uses the haversine formula for straight line distance between two coordinates.
- `travel_minutes` converts km to minutes at 25 km/h, with a minimum of 10 minutes for any hop.

### checks.py

The hard rules the critic and the evals both use.

| Check | Rule | Who fixes it |
|---|---|---|
| `late_arrival` | Arrival plus 45 minutes is after the hotel desk closes, and the hotel has no 24 hour desk | stay |
| `closed_day` | A place is scheduled on its weekly closed day | writer |
| `opening_hours` | A visit starts before opening or ends after closing | writer |
| `long_day` | More than 10 hours of sightseeing in one day | writer |
| `too_much_travel` | More than 60 km of local travel in one day | places |
| `before_arrival` | A place is scheduled before the traveller arrives | writer |
| `misses_return` | A visit ends less than 2 hours before the return journey | writer |

`run_all_checks` runs them all and returns the list.

## 8. Sample data (fixtures/)

| File | Contents |
|---|---|
| `transport.json` | 8 routes: Indore, Mumbai and Bengaluru to Goa, Delhi to Jaipur, Delhi, Mumbai and Indore to Udaipur, Bengaluru to Mysuru. Flights, trains and buses with times and per person prices |
| `stays.json` | 4 to 6 hotels each in Goa, Jaipur, Udaipur and Mysuru, from hostels to luxury, with desk timings |
| `places.json` | 7 to 9 attractions per city with fees, hours, opening times, closed days and coordinates |

The data is realistic but hand made for testing. It is not live pricing.

## 9. Evaluation (evals/)

### make_trips.py

Generates 50 trips with a fixed random seed, so the same trips are produced every time. It cycles through all 8 routes, picks 0 to 4 nights, 1 to 4 travellers and dates from mid November to late December. The budget is a "fair cost" estimate multiplied by one of five levels: 0.6 (very tight), 0.75, 0.9, 1.2 or 1.6 (generous). Output: `trips.jsonl`.

### baseline.py

The systems the multi-agent version is compared against.

- `single_pass` runs the same agents once in a straight line, with no negotiation and no critic. This shows what the loops add.
- `single_llm` gives one model call every option and asks for the whole plan in one go. It only runs when an API key is set. This is the fair comparison for the question "do multiple agents beat one prompt?"

### run_evals.py

Runs every system on every trip and scores them with the same hard checks.

| Metric | Meaning |
|---|---|
| complete plans | Has outbound, return, a hotel (unless a day trip) and a schedule |
| within budget | Complete and not over budget |
| avg overspend when over | How badly plans miss when they do miss |
| plans with zero violations | Complete and passes every hard check |
| avg violations per plan | Total problems divided by plans |
| avg negotiation rounds | How often the coordinator had to step in |
| avg latency, tokens, cost | Speed and price |

It also breaks down results by budget level and by violation type. Output: `results.md` (readable) and `results.json` (raw).

**Current result, LLM off:** the critic loop takes plans with zero violations from 58 percent to 100 percent. Budget fit is the same for both (96 percent), because the two failing trips are impossible even at the cheapest options.

## 10. Tests (tests/)

| File | What it proves |
|---|---|
| `conftest.py` | Switches the LLM off, uses fixtures and dev mode sign in for every test. `make_req` builds a request with sensible defaults. `client` is a test API client, `auth` signs in with a fresh email and returns the header that signed in endpoints need |
| `test_budget.py` | Envelopes add up exactly for awkward budgets like 9,999 and 10,001; day trips get no stay; the food floor works; too low a budget raises an error; bad dates and same city are rejected; totals and overspend are correct and never negative |
| `test_providers.py` | Overnight outbound journeys arrive on the start date; prices scale with travellers; unknown routes raise an error; the fallback wrapper switches to fixtures and records the error |
| `test_checks.py` | The critic's rules catch a closed day, a visit outside opening hours and a late arrival (and blame stay), and a clean plan has no issues |
| `test_graph.py` | End to end: a normal budget fits and passes every check; a tight budget triggers negotiation; a late arrival gets fixed by the critic loop; day trips work; the API returns 200 for a valid plan and 422 for a low budget or free text without a key |
| `fakes.py` | Helpers, not tests. `fake_llm` replaces the Anthropic client with one that returns scripted replies. `answer` makes every agent's LLM call return whatever a test chooses |
| `test_llm.py` | The model wrapper: off without a key, `LLM_MODE=off` wins over a key, JSON is pulled out of chatty replies, a bad reply is retried once with the error, two bad replies or an API error return nothing so agents fall back |
| `test_agents_llm.py` | Every agent with a model connected. Valid choices are used; an out of range transport index, an unknown hotel id, unknown or duplicate place ids, a place set over budget and a coordinator reallocation below the cheapest possible spend are all rejected. Also the stay agent's late check-in filter, its cheapest fallback, missing data and live fallback, the critic's 3 tip limit, the writer's summary and the intake agent |
| `test_serpapi.py` | The live provider with fake HTTP responses: time parsing, missing key, flight and hotel parsing, skipping incomplete results, quota errors, server errors and empty results, and live mode falling back to fixtures with the reason shown in the plan |
| `test_api.py` | Also the profile endpoints (first sign in, cleaning unknown interests, a plan that puts the user's interest first), the learn and model endpoints, and the revise and memory endpoints: a change updates the plan and memory, a question returns no plan, forget empties memory, a new plan uses what was learned, and bad input or a too low budget is refused. Every endpoint: the root redirect; health and routes are public; all four planning endpoints refuse requests without sign in; response shape including sorted options; validation errors; the stream; a full regenerate where the hotel, a journey and the places are changed and every change is kept; PDF download for a normal trip, a day trip and an over budget plan; the docs page offering Bearer sign in |
| `test_auth.py` | Sign up and sign in with a cleaned email and name and a 5 digit ID; only a salted hash is stored; a second account with the same email is refused; bad emails, names, weak passwords and impossible or too young birth dates are rejected; wrong passwords count down, lock after 5 for that address only and the lock lifts after 15 minutes; unknown emails get the same replies; reset codes are emailed, expire, stop after 5 wrong tries, are rate limited and are not sent to banned accounts; a reset signs out old sessions; the session cookie is httpOnly and needs the CSRF header; the secret key is required outside dev; change password needs the current one and signs out other devices; `ADMIN_EMAILS` and the make admin script create admins; missing, garbage, expired, forged and stale tokens are refused; IDs never repeat |
| `test_admin.py` | Plans are saved and regenerating updates the same itinerary; other users cannot see, delete or overwrite them; the stream and the chat save too; only admins reach admin endpoints; finding a user by #ID, name or email with their itineraries; all itineraries with creator and budget, searchable; ban signs the user out and blocks sign in until unbanned; delete removes the user and everything they made; admins cannot ban or delete themselves |
| `test_edits.py` | User choices inside the agents: an unknown journey or hotel falls back with a note; a chosen journey is kept even over budget and becomes the floor; a chosen hotel survives the critic loop; an added place closed on every trip day gets a note; an added place's fee becomes the floor; a note without an LLM is flagged; a far added place becomes an early start day trip on a full day, free places still fit beside it, and there is exactly one note about it with no stale copies |
| `test_rag.py` | The model is saved, reloaded, and retrained if the file is broken; self training waits for 10 examples. Tokens drop stop words and join plurals and synonyms; the index ranks the closest entry first and respects the allowed set; every place and city has a guide entry; search stays in the city; memory turns scores into likes and avoids, recall finds the most similar feedback, forget wipes only that user and old items are trimmed |
| `test_reviser.py` | The chat on Safarnama's own model: clause splitting; remove a place and add a beach; current journeys and hotel stay pinned; cheaper, better rated and named hotels and their limits; switching travel mode; budget and travellers together; "I don't like shopping" removes markets now and keeps them out of a later Jaipur trip; "no museums" removes only museums; adding by description; every explained failure; questions answered from the guide without saving anything; typos; confident parts saved for self training; a correction that makes the model understand a new phrasing and other places with it; Yes saving examples and learned place words; unsure text getting help |
| `test_evals.py` | The eval scripts: trip generation repeats exactly, the single pass baseline has no loops, the single LLM baseline drops unknown ids, and the runner writes its report |

**How the LLM is tested without a key.** Tests never call a real model. `fakes.py` swaps in a fake that returns exactly what the test wants, including wrong answers. This is how the project proves its main safety claim: whatever the model says, code only accepts choices that are valid and fit the budget.

**Coverage.** `pytest` prints a coverage table after every run. `pyproject.toml` sets `--cov-fail-under=85`, so a change that leaves too much code untested fails locally and in CI.

## 11. Frontend (frontend/)

A Next.js app written in TypeScript, in pink and white. It has three pages and talks to the backend over HTTP.

### The user's path

```
/            animated splash, about 3.5 seconds, click or any key to skip
  -> /login       sign in, create account, or forgot password
  -> /welcome     first time only: pick interests
  -> /dashboard   trip form in the middle, Generate itinerary
       -> live agent progress
       -> itinerary: change, remove, add, regenerate, download PDF, chat
  Hi, name menu -> /settings (profile, my itineraries, password, help)
                -> /admin (admins only)
```

The splash goes straight to the dashboard if a session is already saved. The dashboard sends anyone without a session to the login page. If the backend ever answers 401, the session is cleared and the user is sent to the login page with a message that their session ended.

### Files

| File | What it does |
|---|---|
| `app/page.tsx` | The splash. A dotted route line draws itself between two pins, the letters of Safarnama rise one by one, then सफ़रनामा and the tagline fade in. The line is drawn with an SVG mask: a solid line animated with `stroke-dashoffset` reveals a dotted line underneath. For users who ask their system for reduced motion, everything appears at once and the page moves on sooner. The heading has an `aria-label` so screen readers say the word, not nine letters |
| `app/login/page.tsx` | One card with Sign in and Create account tabs, plus a Forgot password view. Create account asks for name, email, date of birth and password; Forgot password asks for the email, then the emailed code and a new password. Passwords have a Show button. After success, a new user goes to the interests page, everyone else to the dashboard. If a saved session is still valid, it goes straight to the dashboard |
| `components/TopBar.tsx` | Safarnama on the left and "Hi, first name" on the right. Clicking it opens a menu with the full name, email and user ID, then Plan a trip, Settings, My itineraries, Interests, Help center, Admin panel for admins, and Sign out. Closes on Escape or a click outside |
| `app/settings/page.tsx` | Profile with the user ID, My itineraries with Open (loads it into the dashboard to keep editing) and Delete, Change password, and the Help center as expandable questions. A side menu jumps between them |
| `app/admin/page.tsx` | Stats, then Users and Itineraries tabs with one search box. Users: a table by ID, name, email, trips and status; clicking a row opens the user with Ban or Unban, Delete account and their itineraries. Itineraries: each row reads like "Indore to Goa itinerary" with dates, amount, budget and "Created by user #ID", which opens that user. Non admins are sent back to the dashboard |
| `components/TripViewer.tsx` | A read only pop up of a saved itinerary: route, travel, hotel and the day by day plan |
| `lib/useAccount.ts` | Shared by the pages: reads the saved session, refreshes the user from the server, and sends anyone signed out or banned to the login page |
| `app/dashboard/page.tsx` | Holds everything: the session, the form values, the user's pinned choices, the plan, which phase the page is in (form, flying or result) and any error. Changing the route clears all pinned choices, since they belong to the old route. Changing the dates clears the pinned journeys. Generating runs the globe animation and the planning at the same time (see below). After a result the itinerary shows first, with "Edit trip details" to bring the form back. Download fetches the PDF and saves it with a readable file name |
| `components/TripForm.tsx` | The centred form: route with valid destinations only, dates (end not before start, at most 14 nights), budget with a per person hint, travellers stepper, interest chips and the note box |
| `components/Itinerary.tsx` | The plan. Total and money left at the top, then four cost figures, then travel and stay rows, each with Change, which opens a list of every alternative with its price. A new pick is marked "new choice" until you regenerate. Each place has Remove, which strikes it through with Undo. Add a place lists everything not already in the plan. Places removed in an earlier round can be brought back. A sticky bar keeps Regenerate and Download PDF in reach while scrolling, and says when there are changes waiting. "See how the agents planned this" opens the agent log |
| `components/Globe.tsx` | The dashboard's background and its show. Draws an outline globe on a canvas: the sphere's edge, latitude and longitude lines, coastlines and country borders, all in pink lines with no fill. It uses d3-geo's orthographic projection, which shows the Earth as a ball seen from space. Canvas rather than SVG, because the whole globe is redrawn 60 times a second while it turns and zooms. While idle it turns slowly at about half strength. The page controls it through four commands, explained below |
| `components/ChatPanel.tsx` | The chat under the itinerary. Your messages on the right, Safarnama's replies on the left with the list of changes and the guide entries it used. Suggestion chips are built from the current plan, such as "Go by bus" when you are on a train. Enter sends, Shift and Enter adds a line. When a reply carries a new plan, the dashboard shows it and updates the form and pinned choices to match, so nothing looks unsaved. The footer shows what Safarnama remembers and a Forget button |
| `components/AgentLog.tsx` | The agent steps as a dotted journey line. An agent that runs a second time gets a hollow pin and the word "again", so the negotiation and critic loops are easy to spot |
| `lib/api.ts` | Types matching the backend's JSON and one function per endpoint. Every call goes through `call`, which adds the token and turns a 401 into an `AuthError`, so pages can tell "signed out" apart from "server unreachable". `streamPlan` reads the server sent events by hand, because the browser's `EventSource` cannot send a POST or an Authorization header. `isDirty` compares the current form and choices with what the plan was made from, which decides whether the button says "Regenerate with my changes" |
| `lib/auth.ts` | Saves, reads and clears the signed in user's details in `localStorage` for showing their name. The session token is never stored here, it lives in an httpOnly cookie. Every access is inside try and catch, because storage can be blocked, for example in some private windows |
| `lib/format.ts` | Indian style rupees (₹12,050), "Rs" to "₹" for backend text, agent names, and date helpers that treat dates as plain `YYYY-MM-DD` strings so time zones never shift a day |
| `scripts/copy-world.mjs` | Copies the country outlines from Natural Earth (public domain), through the `world-atlas` package, into `public/world-110m.json`. The globe loads this file when the page opens, so it is not part of the JavaScript bundle. Run `npm run make:globe` to refresh it |
| `lib/places.ts` | Longitude and latitude of every city in the sample routes. An unknown city aims at the middle of India |
| `app/layout.tsx` | Page title, and imports the two fonts from npm |
| `app/globals.css` | All styling. Colours are variables at the top |

### The Generate animation

Pressing Generate (or Regenerate) does this:

1. **Sucked in.** `suckInto` sets the card's transform origin to the middle of the screen, then rotates it 25 degrees and scales it to 2 percent over 0.9 seconds, with an ease that starts slow and speeds up. The card twists into the centre of the globe.
2. **Zoom to the start.** At the same moment, `globe.travel(from, to)` turns the globe so the starting city faces the screen and zooms in. The zoom depends on the trip: it is picked so the flight will look about 230 pixels long. Indore to Goa is only about 600 km, so without this it would be a few pixels on a whole Earth.
3. **Pin.** A dot and a growing ring mark the start.
4. **Fly.** A dot moves from start to destination along the shortest path over the Earth, leaving a dotted line. The globe turns with it, so the dot stays in the middle, like a camera following a plane.
5. **Land.** A pin and ring mark the destination, and it stays there for a moment.
6. **Spin away.** `globe.finish()` spins the globe faster and faster while it shrinks steadily to a dot and fades.
7. **Open.** The itinerary pops in and `globe.reset()` brings the idle globe back behind it.

**Timing with the agents.** The page waits for both the flight (steps 2 to 5) and the planning to finish before step 6. A fast plan still gets the full animation. A slow plan, for example with an LLM, keeps the globe on the destination while the caption under it shows each agent's step as it streams in. If planning fails, the animation is told to hurry, and the form comes back with the error after about a second.

**Skip.** The caption has "Skip animation", which makes the rest run five times faster.

**Inside the globe,** the animation is a list of tweens: each has a start time, a length and a function that sets the camera (longitude, latitude, zoom, line strength) for a progress value from 0 to 1. Every frame, each tween gets its progress, and when one finishes, the promise for that step resolves. So the page can simply write `await globe.travel(...)` and `await globe.finish()`. Turning always takes the shortest way round (`turnTo`), so the globe never spins the long way to reach a city.

**Reduced motion.** If the user's device asks for less motion, the globe does not turn on its own and every step completes almost at once. The result appears in about half a second.

### Design

- **Colours:** a deep rose pink `#c2185b` for headings, buttons and the route line, on white cards over a very light blush background. The pink was chosen dark enough for white button text to be easy to read. Green for money left, red for over budget.
- **Type:** Yatra One for headings, a display face from an Indian foundry that has both Latin and Devanagari letters, so सफ़रनामा matches the English. Mukta, also from an Indian foundry, for everything else.
- **Fonts are bundled** through the `@fontsource` npm packages, not loaded from Google at run time. The page never waits on another website, works offline, and sends no visitor data to a third party.
- **Motion:** the splash, the slowly turning globe behind the dashboard, and the Generate animation. The idle globe is drawn at about 40 percent strength behind white cards, so the form is always easy to read. The login page stays still.
- **The globe** is drawn from public domain map data rather than a picture, so it stays sharp at any size and has no licence issues on a public repo.
- Works on phones: single column, no sideways scrolling, buttons side by side in the sticky bar. Keyboard focus is always visible.

### Commands

```bash
cd frontend
npm install
npm run dev          # development, http://localhost:3000
npm run make:globe   # refresh the globe outline data
npm run typecheck    # TypeScript check
npm run build        # production build
```

### Bugs found by testing the real flow in a browser

- An expensive place the user added used up the whole sightseeing budget, so even free places were dropped. Fixed in the places agent.
- Far places like Dudhsagar Falls could never be reached in time from a 09:00 start and were always dropped. Fixed with early start day trips in the writer.
- Notes from earlier loop runs stayed in the final plan, so one note named the wrong day. Fixed by making writer and critic notes replace instead of add up.
- On the login page, any failed check of a saved session, even a network blip, deleted the session. Now only a real 401 from the server does.
- Date inputs stopped two column rows from shrinking on narrow phones, causing sideways scrolling. Fixed with `min-width: 0` on grid children.
- The globe went straight from landing into the spin, so the destination was never really seen. Added a short stop on the destination.
- The spin kept the globe zoomed in until the last moment. The shrink now uses a steady exponential scale, so it spins and shrinks together.
- A general layout rule overrode the caption's fixed position and pushed it off screen. Fixed with a more specific rule.

## 12. Configuration and CI

| File | Purpose |
|---|---|
| `requirements.txt` | Python packages |
| `pyproject.toml` | Project name, lint rules (errors, bugs, unused code, old syntax; long prompt lines allowed) and pytest settings: `pythonpath` so tests can import `app`, and coverage with an 85 percent minimum |
| `.env.example` | Every setting with its default. Copy to `.env` |
| `.github/workflows/ci.yml` | Two jobs on every push and pull request. **backend**, on Python 3.11, 3.12 and 3.13: install, lint, test with coverage, run evals, start the API and call two endpoints, then upload the eval report. **frontend**: install, type check and production build |
| `.gitignore` | Keeps the virtual environment, caches and `.env` out of git |
| `LICENSE` | MIT |

## 13. Numbers you can tune

| Constant | File | Value | Effect |
|---|---|---|---|
| `SPLIT` | tools/budget.py | 35/35/15/10 | Starting share for each envelope |
| `FOOD_PER_PERSON_DAY` | tools/budget.py | 500 | Minimum food money |
| `MAX_ROUNDS` | agents/coordinator.py | 3 | Negotiation rounds |
| `MAX_CRITIC_ROUNDS` | agents/critic.py | 2 | Critic rounds |
| `MIN_GAP_HOURS` | agents/transport.py | 4 | Minimum time at the destination |
| `NEARBY_KM` | agents/places.py | 30 | Radius when the critic asks for nearby places |
| `HOURS_PER_DAY`, `FULL_DAY_HOURS` | places.py, writer.py | 7 | Sightseeing hours on a full day |
| `MAX_DAY_KM` | tools/checks.py | 60 | Local travel limit per day |
| `TRANSFER_MIN` | tools/checks.py | 45 | Station or airport to hotel |
| `RETURN_GAP_MIN` | tools/checks.py | 120 | Arrive this early for the return |
| `CITY_SPEED_KMPH` | tools/geo.py | 25 | City travel speed |
| `EARLY_START` | agents/writer.py | 06:30 | When a far away day trip leaves the hotel |
| `FAR_MIN` | agents/writer.py | 120 | Minutes away from the hotel before a place counts as a day trip |
| `MAX_FAILS` | auth.py | 5 | Wrong passwords from one address before that email is locked there |
| `LOCK_SECONDS` | auth.py | 900 | How long a lock lasts |
| `RESET_SECONDS` | auth.py | 900 | How long a reset code works |
| `AUTH_PER_IP` | api.py | 30 | Sign in, sign up and reset requests per address per 15 minutes |
| `PER_USER_PER_DAY` | ml/intent.py | 100 | Training examples one account can add per day |
| `MAX_BODY_BYTES` | api.py | 1,000,000 | Largest request body the API accepts |
| `ITERATIONS` | auth.py | 200,000 | PBKDF2 rounds, set by `PASSWORD_ROUNDS` |
| `MIN_AGE` | auth.py | 13 | Youngest age that can sign up |
| `TOKEN_DAYS` | auth.py | 7 | How long a sign in lasts |

## 14. Questions an interviewer might ask

**Why multiple agents instead of one prompt?**
Each agent has a small, checkable job. When the budget breaks, the coordinator can rerun only the agent that needs to change. When the schedule breaks, the critic sends the problem to the agent that caused it. The evals measure whether this is actually better, rather than assuming it.

**Why does the LLM never do maths?**
Models make arithmetic mistakes, and a trip planner that gets the total wrong is useless. All money, time and distance logic is plain Python. The model only chooses between options that code has already checked.

**What happens if the model returns something wrong?**
It is validated against a schema. Unknown ids, out of range indexes and choices that break the budget or time are rejected. After one retry, the agent uses its rule based pick.

**Why integers for money?**
Floats cannot represent most decimals exactly, so totals drift. Integer rupees always add up.

**How do parallel agents avoid overwriting each other?**
Each writes different fields. Shared fields like `trace` and `floors` use reducers that append or merge instead of replacing.

**What if an API goes down?**
The fallback wrapper switches to sample data, records the error and the user is told. Swapping a data source means adding one provider file.

**How do you test an LLM system without paying for API calls?**
A fake client returns scripted replies, including deliberately wrong ones. The tests check that every wrong answer is rejected and the agent falls back safely. Coverage is 99 percent and CI enforces at least 85.

**How does the frontend show agents working live?**
The backend streams server sent events from LangGraph's step by step output. The frontend reads the stream with `fetch` and adds each step to the journey line as it arrives.

**How is sign in kept safe?**
Passwords are stored only as salted PBKDF2 hashes and compared in constant time. Unknown emails and wrong passwords get the same message. 5 wrong tries from one address lock that email there for 15 minutes. Resets use an emailed code. Sessions are signed JWTs in an httpOnly cookie with a version number, so a password change, reset or ban signs out every device at once.

**How does the admin find a user?**
Every account has a random unique 5 digit ID. The search box takes an ID with or without #, a name or an email. Clicking the user shows their itineraries, and each one opens in full.

**What happens when the user changes the plan?**
Their choices are sent back as pinned ids. Each agent checks for them first and treats them as fixed, and their cost becomes that agent's floor, so the coordinator takes money from the other agents instead. If a choice causes a problem, the user is told instead of being overruled.

**How do you stop infinite loops?**
Hard caps: 3 negotiation rounds, 2 critic rounds and a graph recursion limit of 60. The coordinator also stops as soon as no agent can spend less.

**How does the chat change the plan?**
The message is split into parts. Each part has its places, hotels, kinds, modes and numbers found and swapped for tokens, then Safarnama's own intent model decides what the part asks for. The revise agent turns that into edits with ids, the edits become pinned choices on the request, and the normal agent graph replans. The reply is a diff of the old and new plans, so it can only report what really changed.

**Why your own model instead of an LLM?**
No key, no per message cost, no data leaving the server, answers in milliseconds, and every decision can be inspected and corrected. The trade off is flexibility, which the feedback loop slowly makes up for.

**How does it learn?**
Three ways. Confident predictions are saved as examples (self training). Yes saves a reply's sentences with double weight. Not right lets the user pick the right intent, which is saved with triple weight and removes wrong automatic copies. The model retrains from the seed sentences plus every saved example and is written to disk, so learning survives restarts and is shared by all users. What a user likes is kept per user.

**Why mask entities before classifying?**
So the model learns how people ask, not which places exist. "I dont wanna go to `_place_`" learned in Goa works for any place in any city, and new places in the data need no retraining.

**Where is the RAG?**
The travel guide is retrieved for questions and vague requests like "somewhere for photography", and answers quote the entry they came from. Words from vague requests that the user confirmed are attached to the place they found, so retrieval improves with use. The traveller's own past feedback is retrieved the same way and given to the planners.

**How do the interests work?**
On first sign in the user picks from 14 interests. Each has a set of words, which are matched against a place's category and guide tags. The places agent adds a bonus to a place's score for every matching interest, up to three, and says which interests it planned around.

## 15. Known limitations

- Rate limits are kept in memory, so they reset on restart. Several servers should share them through Redis.
- All data is in one SQLite file. A larger deployment should move to PostgreSQL.
- The PDF writes "Rs" instead of "₹", because the built in PDF fonts lack the rupee sign.

- Sample data is hand made, so evals measure the logic, not real world prices.
- The rule based negotiation only ever cuts spending. It never upgrades the plan when money is left over.
- Live mode covers flights and hotels only. Trains and buses use sample data.
- Distances are straight lines, not road distances.
- The writer's nearest place first approach is simple and fast but not guaranteed to find the best order.

## 16. Chat, RAG, learning and interests

### app/db.py
One SQLite file (`SAFARNAMA_DB`) with five tables: `profiles` (interests and whether the first sign in page was done), `feedback` (changes that taught a like or avoid), `examples` (training sentences learned from use), `turns` (each chat message and how it was understood, so feedback can refer to it) and `place_words` (words learned for a place). Every connection is opened and closed per call.

### app/ml/entities.py
`tag(text, places, stays, city)` finds what a sentence talks about. Each place or hotel name is reduced to its distinctive words (city names and words like fort, beach and hotel are left out), and a word in the sentence counts if it matches exactly or is at least 80 percent similar, so typos still work. When a place and a hotel both match ("Fort Aguada" and "Taj Fort Aguada"), the one with more of its name covered wins. Kinds of place, travel modes and numbers (with "25k" read as 25000) are found too. The result has the ids and a masked sentence like `remove _place_`.

### app/ml/seed.py
About 700 starting sentences for 12 intents, made from hand written templates with polite openings, endings and deliberate typos. `LABELS` gives each intent the name shown in the app.

### app/ml/intent.py
- `build` makes a scikit-learn pipeline: word TF-IDF (1 and 2 word phrases) plus character TF-IDF (2 to 5 letters, which handles typos), then logistic regression.
- `train` fits it on the seed sentences plus every saved example, weighted by source (seed 1, automatic 0.5, confirmed 2, corrected 3), and saves it with joblib.
- `model` returns the cached model if its stamp matches the examples in the database, loads it from disk if the saved stamp matches, or retrains. The stamp ignores automatic examples until 10 more arrive, so self training does not retrain on every message.
- `predict` returns the intent and its probability. Below 0.45 it says "other".
- `add_examples` and `stats` save examples and report what the model has learned.

### app/agents/reviser.py
- `clauses` splits a message on punctuation and words like "and" and "then", keeps "26,500" together, and rewrites "replace A with B" as "remove A, add B".
- `understand` tags and classifies each part. `act` carries out one part: add or remove places (named, by kind, or by description through the guide), choose a cheaper, better rated or named hotel, switch travel mode, set the budget or travellers, record a like or dislike, or answer a question from the guide.
- `revise` runs every part, saves confident parts as automatic examples, saves likes and avoids, stores the turn, replans with `plan_trip(request, learned)` and writes the reply from `diff`.
- `learn` takes the feedback for a turn: Yes saves its parts as confirmed and its found places' words to `place_words`. A correction saves the chosen intents and deletes matching automatic examples. Then it retrains.

### app/rag/guide.py and app/rag/memory.py
The guide index is rebuilt (and cached) whenever learned place words change, so a confirmed "somewhere romantic" makes that place easier to find. `memory.profile` returns likes, avoids, the most relevant past messages and the user's interests in one `Learned` object.

### app/profile.py
The 14 interests, each with a label, a short hint and the words it matches. `matches(interests, place_id, category)` lists which interests a place fits. `TO_CATEGORY` maps interests to the form's interest chips, so the dashboard starts with them ticked.

### Frontend
- `app/welcome/page.tsx` is the first sign in page and the Interests page. Cards with line icons toggle on and off, Save goes to the dashboard, and Skip for now is offered only the first time.
- The login page sends a new user to it, and the dashboard also checks the profile and redirects if the page was never finished.
- `components/InterestIcon.tsx` has one small line drawing for each interest.
- `components/ChatPanel.tsx` shows "I understood: ..." under each reply with Yes and Not right buttons. Not right opens a picker for each part of the message. Teach me and try again sends the correction, puts the plan back as it was before that reply and sends the message again, so the user sees the model fix its own mistake. The footer shows how many examples the model has learned.

## Explore, photos, bookings and friends

| File | What it does |
|---|---|
| `fixtures/explore.json` | For each destination: a tagline, travel information (intro, understand, get around, best time, stay safe), top places, and restaurants, cafes and photo spots with area, short text, price level, a dish to try and neighbourhood level coordinates. For each route: the road and the stops on the way. `wiki` holds the Wikipedia article title used for photos |
| `app/explore.py` | Turns that file and `places.json` into cards that all have the same shape. `stops` puts route stops in travel order by projecting each one onto the line from start to destination, so the same list works in both directions. `meals` picks the nearest restaurant and cafe to each day's sights, within 8 km, without repeating |
| `app/media.py` | Fetches a photo and a short summary from the Wikipedia REST API with a descriptive User-Agent, keeps only images from `upload.wikimedia.org`, and caches hits for 30 days and misses for an hour in `wiki_cache`. `/media/{id}` only looks up titles listed in the explore data, so it cannot be used to fetch anything else |
| `app/flights.py` | Reads pasted booking text with regular expressions: the flight number and airline, or a train number, or a bus; airport codes, city and station names; dates in several formats; and the first two times as departure and arrival, adding a day when the arrival is earlier or marked +1 |
| `MyJourney` in `app/state.py` | A journey the traveller already booked. It moves the trip's start to the landing day, keeping the trip length, or the end to the return day. The transport agent treats it as pinned and only searches for the other leg |
| `app/trips.py` | Sharing. `trip_members` lists friends on a trip and `trip_invites` keeps a SHA-256 hash of each invite token with a 7 day expiry. Members can view and save the trip; only the planner can delete it or turn off links. At most 10 people per trip and 20 links per trip per day |
| `frontend/components/Photo.tsx` | Loads a photo only when the card scrolls near the screen, fades it in, and shows drawn artwork for its kind when there is none |
| `frontend/components/PlaceSheet.tsx` | The details sheet: photo, text, tip, an OpenStreetMap map and Google Maps buttons. It slides up from the bottom on phones and fades in on larger screens |
| `frontend/components/StopsOnTheWay.tsx`, `BookingPaste.tsx`, `Friends.tsx` | The stops strip, the paste your booking form, and the travelling together panel with Gmail, copy and email buttons |
| `frontend/app/explore/page.tsx`, `frontend/app/join/[token]/page.tsx` | The Explore page and the page a friend lands on from an invite link. Signed out friends go to sign in and come straight back |

**Smoother globe.** The globe now has a goal camera and a view camera. Animations move the goal, and every frame the view moves a fixed share of the way towards it (`1 - exp(-dt * 7)`), so there are no sudden stops between the zoom, the flight and the spin away. The final spin is 160 degrees instead of 900, the dotted route line flows, and the canvas resolution is capped at 2x for steady frames on phones.


## Real data

| File | What it does |
|---|---|
| `scripts/build_explore.py` | Downloads the Wikivoyage guide for 41 destinations (raw page text, one request at a time, with a descriptive User-Agent, cached on disk). It keeps the intro and the Understand, Get in, Get around and Stay safe sections, and turns the See, Do, Eat and Drink listings into cards. Cafes are Eat or Drink listings that mention coffee, tea, bakeries and the like. Photo spots are sights whose name or text mentions viewpoints, sunsets, lakes, falls, ghats, beaches or peaks. Big cities are split into district pages, so it follows them |
| `scripts/build_stops.py` | Gets the real road for each route from OSRM (OpenStreetMap), collects the towns and destinations listed on Wikivoyage region pages for the states the road crosses, and keeps up to 10 that lie within 45 km of the road, spread out along it. Each stop gets its Wikivoyage intro, photo and first Eat listing |
| `app/google_places.py` | Optional live mode. Text Search for each category near the city, ranked by rating and number of reviews; photos through the Places photo endpoint; and stops through Search Along Route using the OSRM road line. Answers are kept in memory for an hour |
| `frontend/app/manifest.ts`, `public/sw.js`, `public/icons/` | Make the site installable as a phone app: name, icons, theme colour, full screen display, and a service worker that keeps built files on the phone |
