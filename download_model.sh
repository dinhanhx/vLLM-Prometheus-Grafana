export HF_HOME=${PWD}/.cache/huggingface 
export HF_TOKEN="your huggingface api key goes here"

huggingface-cli download $1 