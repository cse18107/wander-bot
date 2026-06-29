#!/usr/bin/env bash
# Create the Bedrock Guardrail for the Roam travel assistant.
# Requires: AWS CLI configured with an IAM user that has bedrock:CreateGuardrail.
#
#   ./create-guardrail.sh
#
# Prints the new guardrail ID at the end — put it in WB_BEDROCK_GUARDRAIL_ID.
set -euo pipefail

REGION="${AWS_REGION:-ap-south-1}"
NAME="${GUARDRAIL_NAME:-roam-guardrail}"

echo "==> Creating guardrail '${NAME}' in ${REGION}"

aws bedrock create-guardrail \
  --region "${REGION}" \
  --name "${NAME}" \
  --description "Guardrail for the Roam travel assistant" \
  --blocked-input-messaging "I'm here to help with travel planning, so I can't assist with that request." \
  --blocked-outputs-messaging "I'm here to help with travel planning, so I can't share that." \
  --content-policy-config '{
    "filtersConfig": [
      {"type": "SEXUAL",        "inputStrength": "HIGH",   "outputStrength": "HIGH"},
      {"type": "VIOLENCE",      "inputStrength": "HIGH",   "outputStrength": "HIGH"},
      {"type": "HATE",          "inputStrength": "HIGH",   "outputStrength": "HIGH"},
      {"type": "INSULTS",       "inputStrength": "MEDIUM", "outputStrength": "MEDIUM"},
      {"type": "MISCONDUCT",    "inputStrength": "HIGH",   "outputStrength": "HIGH"},
      {"type": "PROMPT_ATTACK", "inputStrength": "HIGH",   "outputStrength": "NONE"}
    ]
  }' \
  --sensitive-information-policy-config '{
    "piiEntitiesConfig": [
      {"type": "EMAIL",                    "action": "ANONYMIZE"},
      {"type": "PHONE",                    "action": "ANONYMIZE"},
      {"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
      {"type": "CREDIT_DEBIT_CARD_CVV",    "action": "BLOCK"},
      {"type": "CREDIT_DEBIT_CARD_EXPIRY", "action": "BLOCK"},
      {"type": "US_BANK_ACCOUNT_NUMBER",   "action": "BLOCK"},
      {"type": "US_SOCIAL_SECURITY_NUMBER","action": "BLOCK"},
      {"type": "PASSWORD",                 "action": "BLOCK"},
      {"type": "PIN",                      "action": "BLOCK"}
    ]
  }' \
  --word-policy-config '{
    "managedWordListsConfig": [{"type": "PROFANITY"}]
  }' \
  --query 'guardrailId' --output text

echo
echo "==> Done. Copy the guardrail ID printed above into your .env:"
echo "    WB_BEDROCK_GUARDRAIL_ID=<that id>"
echo "    WB_BEDROCK_GUARDRAIL_VERSION=DRAFT"
