export interface Env {
  ASSETS: Fetcher;
  BUCKET: R2Bucket;
  /** e.g. "myteam.cloudflareaccess.com" (Zero Trust -> Settings -> Custom pages shows the team domain). */
  ACCESS_TEAM_DOMAIN?: string;
  /** The Access application's "Application Audience (AUD) Tag". */
  ACCESS_AUD?: string;
  /** "true" disables the Access check. Only for `wrangler dev` (see .dev.vars). */
  ALLOW_UNAUTHENTICATED?: string;
}

/** Things tests (and nothing else) replace. */
export interface Deps {
  fetch: typeof fetch;
  now: () => Date;
}
