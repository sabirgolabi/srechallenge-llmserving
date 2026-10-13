import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://qwen-llm-serve-svc.llm-serving.svc.cluster.local:8000';
const MAX_NEW = parseInt(__ENV.MAX_NEW_TOKENS || '32');

const prompts = [
  'What is Kubernetes?',
  'Explain what a load balancer does.',
  'Write a short poem about the ocean.',
  'Give me three tips for learning Python.',
  'What is the difference between TCP and UDP?',
  'Describe how a REST API works.',
  'Why is the sky blue?',
  'Summarize the plot of Romeo and Juliet in two sentences.',
  'What are the benefits of unit testing?',
  'How does DNS resolve a domain name?',
  'Explain recursion to a beginner.',
  'What is a container image?',
];

// Ramp 1 -> 2 -> 4 -> 8 virtual users (about 6 minutes in total).
export const options = {
  stages: [
    { duration: '30s', target: 1 },
    { duration: '1m', target: 2 },
    { duration: '2m', target: 4 },
    { duration: '2m', target: 8 },
    { duration: '30s', target: 0 },
  ],
};

export default function () {
  // Random prompt + random number so every request is unique (no prefix-cache effects).
  const prompt =
    prompts[Math.floor(Math.random() * prompts.length)] +
    ' (' + Math.floor(Math.random() * 100000) + ')';

  const res = http.post(
    `${BASE}/generate`,
    JSON.stringify({ prompt: prompt, max_new_tokens: MAX_NEW }),
    { headers: { 'Content-Type': 'application/json' }, timeout: '120s' },
  );

  check(res, {
    'status 200': (r) => r.status === 200,
    'has text': (r) => {
      try { return typeof r.json('text') === 'string'; } catch (e) { return false; }
    },
  });
}
