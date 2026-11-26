# WhatsApp approvals

People can approve, edit, stop and answer what their AI employees send them from WhatsApp. Each
message has everything needed to decide, so they rarely need to open Autopilot. This page is for
whoever runs Autopilot: you set up **one** WhatsApp Business number for the whole platform (like the
Composio key), and then every user connects their own phone in **Settings → WhatsApp**.

Code: `backend/app/services/whatsapp.py` (messages, delivery, replies), `backend/app/api/whatsapp.py`
(settings and the webhook), `backend/app/services/decisions.py` (the same decision rules as the
Needs you inbox).

## What people get

- **Approvals**: what the AI employee wants to do, with the exact post, email or article, why it's
  asking, the quality score, and **Approve / Edit / Decline**. Edit sends the current text as its own
  message (easy to copy), and the reply becomes the new version. Decline asks for an optional reason,
  which the AI employee reads.
- **Heads-ups**: what will go out and when, with **Send now / Edit / Stop it**. Stopping happens
  immediately, and a reason can follow.
- **Questions**: the options as buttons (or a list), or just reply with an answer.
- **Hand-ins (PRDs, analyses)**: the full text as messages, then **Approve / Edit / Ask for changes**.
- **Team lead suggestions**: the current and proposed target, with **Approve / Change number / Keep as is**.
- **App connections and website sign-ins**: the link or instructions, then **I've connected it / I've signed in**.
- **Replying to any message** about a request makes it a comment ("Approve + comment") or the new
  text ("Use as new text").
- **One at a time**: after each decision, the next waiting request follows straight away. Sending
  "list" shows everything that's waiting.
- **Earned trust**: after approving several of the same kind unchanged, it offers to switch that kind
  of action to a heads-up (or to "on its own") for the goal. It never changes this by itself.

Still decided in Autopilot, with the details and a link straight to the request: **spending money,
merging code and deleting things**. A tap on a phone shouldn't do those.

## Meta's rules, and how they're handled

- **Opt-in**: people connect by sending our number a one-time code from their own phone (Settings
  gives them a wa.me link that fills it in). That proves the number is theirs and is their opt-in.
  Sending "stop" disconnects them.
- **The 24-hour window**: after someone writes or taps a button, we may send anything for 24 hours.
  Inside it, every request arrives as a full card. Outside it, the first message must be one of the
  approved **templates** below. One tap on it reopens the window, and the rest follows as normal cards.
  At most one template goes out every 4 hours while it's unanswered, so a quiet day never turns into
  a stream of messages.
- **Business use only**: Meta bars general-purpose AI chatbots on the Business API. This is a
  workflow for our product, not a chatbot: free text is only ever taken as an answer, an edit, a
  reason or a comment on a request. Anything else gets a short reply pointing to what's waiting.
- **Cost**: Meta charges per template message (the price depends on the country). Messages inside the
  24-hour window, which is most of them for people who are active, are free.

## Setting it up

1. **Meta app and number.** In [Meta for Developers](https://developers.facebook.com/apps), create an
   app of type *Business* and add the **WhatsApp** product. Add and verify a phone number for the
   business (one that isn't already on WhatsApp), and set its display name.
2. **A permanent token.** In Business Settings → System users, create a system user, give it the app
   and the WhatsApp account, and generate a token with `whatsapp_business_messaging` and
   `whatsapp_business_management`.
3. **Settings** (in `.env`, or the Render environment group):

   | Setting | Where to find it |
   |---|---|
   | `WHATSAPP_ACCESS_TOKEN` | The system user token from step 2 |
   | `WHATSAPP_PHONE_NUMBER_ID` | WhatsApp → API Setup → Phone number ID |
   | `WHATSAPP_BUSINESS_NUMBER` | The number itself, e.g. `+14155550100` |
   | `WHATSAPP_APP_SECRET` | App settings → Basic → App secret (checks webhook signatures) |
   | `WHATSAPP_VERIFY_TOKEN` | Any long random string you choose |
   | `WHATSAPP_WABA_ID` | WhatsApp → API Setup → WhatsApp Business Account ID (only for step 5) |

4. **Webhook.** WhatsApp → Configuration → Webhook: callback URL
   `https://<your API address>/api/whatsapp/webhook` (on Render, the autopilot-api URL; going through
   the app's address works too) and the verify token from step 3. Subscribe to the **messages** field.
5. **Templates.** Run `python -m app.cli whatsapp-templates` from `backend/` (on Render: the API's
   Shell). It submits the four utility templates below for review, which usually takes minutes. Check
   them in WhatsApp Manager → Message templates.
6. **Try it**: in Autopilot, Settings → WhatsApp → Connect WhatsApp, then send the message it fills in.

## Templates

They're defined in `whatsapp.TEMPLATES`. If you edit them there, submit them again. All are in the
**Utility** category, and each button carries a signed payload set per message.

| Template | Used for | Buttons |
|---|---|---|
| `autopilot_approval` | An approval when the window is closed | Approve, Show details, Decline |
| `autopilot_heads_up` | A heads-up when the window is closed | Stop it, Show details, Send now |
| `autopilot_question` | A question when the window is closed | Answer, Skip |
| `autopilot_waiting` | Anything else (and what's decided in the app) | Show me |

"Approve" on a template only approves right away when the template showed the whole content.
Otherwise it shows the full card first.

## Security

- Each button carries a token signed with the app's secret key and bound to that request and person.
  A forwarded message or a made-up payload can't approve anything.
- Replies are only accepted from the connected number of someone allowed to decide that request (the
  same rules as the inbox). Every webhook call must carry Meta's signature.
- Every decision made on WhatsApp is in the goal's work log, marked as made on WhatsApp.
