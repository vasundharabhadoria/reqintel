ALTER TABLE public.users DROP COLUMN IF EXISTS password_hash;
CREATE TABLE public.repository_versions (
 id uuid primary key default gen_random_uuid(),
 project_id uuid not null references public.projects(id) on delete cascade,
 version_number integer not null, is_current boolean not null default true, change_summary text,
 total_requirements integer not null default 0, approved_requirements integer not null default 0,
 pending_requirements integer not null default 0, rejected_requirements integer not null default 0,
 new_count integer not null default 0, modified_count integer not null default 0, deleted_count integer not null default 0,
 changes jsonb not null default '{"new": [], "deleted": [], "modified": []}', snapshot jsonb not null default '[]',
 documents jsonb not null default '[]', created_by uuid references public.users(id) on delete set null,
 created_at timestamptz not null default now());
CREATE TABLE public.requirement_issue_waivers (
 id uuid primary key default gen_random_uuid(),
 requirement_version_id uuid not null references public.requirement_versions(id) on delete cascade,
 rule_name varchar not null, reason text, created_by uuid references public.users(id) on delete set null,
 created_at timestamptz not null default now());
ALTER TABLE public.repository_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY repository_versions_owner_all ON public.repository_versions FOR ALL
 USING (EXISTS (SELECT 1 FROM projects p WHERE p.id = repository_versions.project_id AND p.owner_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid))
 WITH CHECK (EXISTS (SELECT 1 FROM projects p WHERE p.id = repository_versions.project_id AND p.owner_id = (NULLIF(current_setting('app.current_user_id', true), ''))::uuid));
GRANT SELECT,INSERT,UPDATE,DELETE ON public.repository_versions, public.requirement_issue_waivers TO reqintel_app;

-- Disposable-test credentials only (the script refuses to run against anything but a local *test* database).
ALTER ROLE reqintel_app LOGIN PASSWORD 'testpw';
