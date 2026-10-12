/** Browser publication scope, not server authorization. Each keyed workspace owns one. */
export type NesteggRequestScope = { ownerId: string; sessionId: string; isCurrent: () => boolean };
export function createNesteggWorkspaceScope(ownerId: string, sessionId: string) {
  let active = false;
  let revision = 0;
  return {
    activate() { active = true; revision += 1; },
    dispose() { active = false; revision += 1; },
    isCurrent() { return active; },
    capture(): NesteggRequestScope {
      const captured = revision;
      return { ownerId, sessionId, isCurrent: () => active && revision === captured };
    },
  };
}
