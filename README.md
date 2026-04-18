# Ludomancer

Ludomancer is a desktop app that analyzes your Steam library and helps you pick backlog games.

## Required API setup

These values are required to launch the app:

- STEAM_API_KEY
- STEAM_ID64

For LLM recommendations in the app, add at least one of:

- ANTHROPIC_API_KEY
- OPENROUTER_API_KEY

## How to get each value

1. STEAM_API_KEY
	- Sign in at https://steamcommunity.com/dev/apikey
	- Create a key (localhost is fine for the domain field)

2. STEAM_ID64
	- Use your numeric Steam profile ID
	- If your profile uses a custom URL, resolve it at https://steamid.io

3. ANTHROPIC_API_KEY (optional, for Ask LLM)
	- Create a key at https://console.anthropic.com

4. OPENROUTER_API_KEY (optional, for Ask LLM)
	- Create a key at https://openrouter.ai/keys

## Configure environment

Copy the example file and fill in your values:

~~~bash
copy .env.example .env
~~~

Minimum required .env entries:

~~~env
STEAM_API_KEY=your_steam_web_api_key
STEAM_ID64=your_steam_id64
~~~

Optional LLM entries:

~~~env
ANTHROPIC_API_KEY=
OPENROUTER_API_KEY=
~~~

## Install and run

~~~bash
poetry install
poetry run ludomancer
~~~

## Notes

- The app starts only when STEAM_API_KEY and STEAM_ID64 are set.
- Ask LLM requires at least one LLM key.
