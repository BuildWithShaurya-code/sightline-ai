// Fail the public frontend build if it would point at localhost or a missing API.
// Server-only credentials are never read or printed here.
import { isIP } from 'node:net';
import { pathToFileURL } from 'node:url';

export function publicOrigin(value, name) {
  let url;
  try { url = new URL(value); } catch { throw new Error(`${name} must be an HTTPS origin.`); }
  const host = url.hostname.toLowerCase().replace(/^\[|\]$/g, '');
  if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash || url.pathname !== '/' || url.port || isIP(host) || host === 'localhost' || !host.includes('.') || /\.(local|localhost|internal|test|example|invalid)$/.test(host)) {
    throw new Error(`${name} must be a public HTTPS origin without a path or credentials.`);
  }
  return url.origin;
}

export function checkVercelEnvironment(env) {
  const sameOrigin = env.VITE_CLOUD_UPLOADS === '1' && !env.VITE_API_URL;
  const api = sameOrigin ? 'same-origin-services' : publicOrigin(env.VITE_API_URL, 'VITE_API_URL');
  const project = publicOrigin(env.VITE_SUPABASE_URL, 'VITE_SUPABASE_URL');
  if (!project.endsWith('.supabase.co')) throw new Error('VITE_SUPABASE_URL must identify the intended Supabase project.');
  const key = env.VITE_SUPABASE_PUBLISHABLE_KEY || '';
  if (!/^sb_publishable_[A-Za-z0-9_-]+$/.test(key)) throw new Error('Configure the Supabase publishable key for the frontend.');
  for (const [name, value] of Object.entries(env)) {
    if (name.startsWith('VITE_') && (/SECRET|SERVICE_ROLE|PRIVATE|PASSWORD|TOKEN/i.test(name) || /sb_secret_|"role"\s*:\s*"service_role"/.test(value || ''))) {
      throw new Error('A server-only setting is exposed through a VITE_ variable. Remove it before deployment.');
    }
  }
  if (env.VERCEL_URL && api === `https://${env.VERCEL_URL}`) throw new Error('This configuration requires the durable backend origin; it must not loop to the static frontend.');
  return {api, project};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    checkVercelEnvironment(process.env);
    console.log('Public frontend configuration validated. This does not certify backend readiness.');
  } catch (error) {
    console.error(`Vercel preflight failed: ${error.message}`);
    process.exitCode = 1;
  }
}
