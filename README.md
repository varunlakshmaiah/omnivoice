# 🌌 OmniVoice — Open-Source Alexa LLM Skill

[![Alexa-Hosted](https://img.shields.io/badge/Alexa--Hosted-Compatible-brightgreen.svg?style=for-the-badge&logo=amazon-alexa)](https://developer.amazon.com/alexa/console/ask)
[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg?style=for-the-badge&logo=python)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)
[![LLMs](https://img.shields.io/badge/LLMs-OpenAI%20%7C%20Gemini%20%7C%20Llama%20%7C%20DeepSeek-orange.svg?style=for-the-badge)](https://openrouter.ai/)

OmniVoice is a zero-friction, fully generic, and highly optimized open-source Alexa skill that connects your Amazon smart speaker to **any OpenAI-compatible Large Language Model (LLM)**. Ditch the rigid, pre-programmed voice commands and turn your Alexa into a fluid, highly intelligent, and sardonically witty personal AI assistant.

<p align="center">
  <img src="images/hero.png" alt="OmniVoice Header Banner" width="100%" />
</p>

---

## ⚡ Architecture Flow

```
User 🗣️ ➔ Alexa Smart Speaker ➔ AWS Lambda (Python) ➔ LLM Provider ➔ Response ➔ Alexa Speaks ➔ User 👂
```

---

## ✨ Features

- **🧠 Open & Bounded Text Capture:** Uses custom `AMAZON.SearchQuery` slots paired with a highly comprehensive list of conversational starting prefixes so that all natural questions and follow-ups pass completely untruncated to your LLM.
- **⚡ Ultra Low-Latency Handling:** Integrated with progressive voice responses ("*Working on it, Sir...*") to keep the Alexa session fully alive while the LLM generates a response.
- **🛡️ Secure and Private:** Absolutely zero hardcoded secrets. All sensitive API keys and configuration parameters are secured via `.env` variables (fully ignored in `.gitignore`).
- **💬 Session Memory:** Automatically maintains conversational history (up to the last 10 turns) inside session attributes for fluid, multi-turn follow-ups, with active token truncation to stay within Alexa's strict 24KB limit.
- **🌍 Global Support:** Complete localization models for major English-speaking regions: **US, UK, Canada, Australia, and India**.
- **📅 Timezone-Aware System Prompt:** Automatically injects the correct date, day, and local time into the system instructions so the LLM is always context-aware.

---

## 📁 Repository Structure

```text
omnivoice/
├── lambda/
│   ├── lambda_function.py   # Skill handlers, system prompt builder, LLM API client
│   ├── requirements.txt     # Python dependencies (Alexa SDK, requests, urllib3)
│   └── .env.example         # Template for environment configuration
├── skill-package/
│   ├── skill.json            # Skill manifest (generic & ready for Alexa-Hosted import)
│   └── interactionModels/
│       └── custom/
│           ├── en-US.json    # US English interaction model & carrier phrases
│           ├── en-AU.json    # Australian English interaction model
│           ├── en-CA.json    # Canadian English interaction model
│           ├── en-GB.json    # British English interaction model
│           └── en-IN.json    # Indian English interaction model
├── images/
│   └── hero.png             # Premium branding image
├── .gitignore               # Ensures environment variables and state are never committed
└── README.md                # Premium developer documentation
```

---

## 🚀 Quick Start (Deploy in 5 Minutes)

You can run OmniVoice completely for free using **Alexa-Hosted Skills** (Amazon hosts the backend Lambda function for you, no AWS account billing needed!).

### Step 1: Create the Skill
1. Log in to the [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Click **Create Skill**, name it **OmniVoice**, and select your default language.
3. Select **Custom** for the model, and choose **Alexa-Hosted (Python)** for the hosting method.
4. Scroll down to **Choose a method to import code**, select **Import from Git**, and paste your GitHub clone URL:
   `https://github.com/your-username/omnivoice.git`
5. Click **Create Skill** and wait for the setup to complete.

### Step 2: Configure Environment Variables
1. Once inside your skill dashboard, go to the **Code** tab in the top navigation.
2. In the file explorer, duplicate `.env.example`, rename it to `.env`, and fill in your variables:
   ```ini
   LLM_API_KEY=your_openai_or_openrouter_api_key_here
   LLM_BASE_URL=https://openrouter.ai/api/v1/chat/completions
   LLM_MODEL=google/gemini-2.5-flash:free
   ```
3. Click **Save** and then **Deploy** in the top-right corner.

### Step 3: Build the Interaction Model
1. Go to the **Build** tab in the top navigation.
2. Click **Build Model** in the right-hand panel. This compiles the custom NLU structure and invocation name (`"omni voice"`).
3. Once the build succeeds, head to the **Test** tab, set testing to **Development**, and say:
   > *"Alexa, open Omni Voice"*

---

## 🛠️ Advanced Configuration (`.env`)

Configure your assistant behavior by updating the environment variables inside your `.env` file (or your Lambda Environment settings):

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_API_KEY` | *(required)* | Your API Key (OpenRouter, Groq, OpenAI, etc.). |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1/chat/completions` | Base endpoint URL for OpenAI-compatible client. |
| `LLM_MODEL` | `google/gemini-2.5-flash:free` | Model identifier (use fast models for best experience). |
| `LLM_MAX_TOKENS` | `200` | Limits vocal response length (voice responses should be concise). |
| `LLM_MAX_HISTORY_TURNS` | `10` | Conversation memory depth (number of turns to retain). |
| `LLM_UTC_OFFSET` | `5.5` | System clock timezone offset (e.g. `5.5` for IST, `-5` for EST). |

---

## ⚠️ Troubleshooting & Warnings Guide

Voice-based AI systems have strict timeouts and execution rules. Review these guidelines to resolve common issues:

### 1. The Strict 8-Second Alexa Timeout Limit
> [!IMPORTANT]
> **Alexa has a hard platform timeout limit of 8 seconds.** If your backend code does not return a fully formed response to Alexa's servers within 8 seconds, the Echo device will crash, shut down, or say: *"There was a problem with the requested skill's response."*

*   **The Cause:** Choosing slow models (like large reasoning models like DeepSeek-R1 or highly congested free endpoints) can easily take 10 to 15 seconds to reply.
*   **The Symptom:** You see `"LLM API timeout"` errors in your logs, and OmniVoice says: *"I'm afraid that query took longer than expected, Sir."*
*   **The Fix:** Always use high-speed, low-latency models. We highly recommend:
    - **Google Gemini 2.5 Flash** (`google/gemini-2.5-flash:free`) on OpenRouter (1–2s response time).
    - **Groq API** (`llama-3.3-70b-specdec` or `llama3-8b-8192` via `https://api.groq.com/openai/v1/chat/completions`) which yields incredibly fast sub-second voice responses.

### 2. Preventing Abrupt Skill Exits
> [!WARNING]
> If a user speaks a custom follow-up query that does not map to your list of interaction model phrases, Alexa will immediately exit the skill session instead of asking your LLM.

*   **The Cause:** Alexa requires carrier phrases (e.g. `"ask {query}"`) to pass unconstrained speech to `AMAZON.SearchQuery`. If a user says something completely unmatched (like a single random word), Alexa will drop the connection.
*   **The Fixes:** 
    1.  We have included a massive list of **conversational carrier phrases** (e.g. `"and {query}"`, `"is {query}"`, `"can {query}"`, `"more {query}"`) covering 99% of English conversational starters.
    2.  We configured `"fallbackIntentSensitivity"` to `"HIGH"` in the interaction model. This forces Alexa to route unmatched utterances to `AMAZON.FallbackIntent` where our backend politely reprompts the user, keeping the session open rather than crashing.

### 3. Silent Skill Crashes
*   If Alexa immediately shuts down with no spoken error:
    - Check your API key. If your LLM provider's balance is `$0`, the API will return a `401 Unauthorized` or `402 Payment Required` code, leading to a crash.
    - Check your AWS CloudWatch / Alexa Developer Code console logs. Make sure that your `.env` variables are correctly written with **no spaces** around the `=` signs.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
