python3 data/cached_challenge_fineweb.py --variant sp1024
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.4/install.sh | bash
source ~/.bashrc
runpodctl config
runpodctl config --apiKey=$RUNPOD_API_KEY
nvm install node
npm i -g @openai/codex

# github cli
curl -sS https://webi.sh/gh | sh; \
source ~/.config/envman/PATH.env
echo $GITHUB_API_KEY | gh auth login --with-token
