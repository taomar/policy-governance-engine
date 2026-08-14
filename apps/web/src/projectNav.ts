/**
 * The one way to say "open this project" to the navigation handler.
 *
 * This prefix already existed inside `App.tsx`, where the sider used it to open
 * a named project while every other surface could only ask for the register.
 * That is why the dashboard's readiness rows carried a right-arrow each and all
 * went to the same generic list: the destination they needed was reachable, but
 * not importable. Moving the two lines here makes a row able to navigate to the
 * thing it names, and keeps one definition of the target format instead of a
 * string literal repeated per call site.
 */
export const PROJECT_NAV_PREFIX = "project:";

/** Navigation target that opens the project with this key. */
export function projectNavTarget(key: string): string {
  return `${PROJECT_NAV_PREFIX}${key}`;
}

/**
 * The project key inside a navigation target, or null if the target is a page.
 */
export function projectKeyFromNavTarget(target: string): string | null {
  return target.startsWith(PROJECT_NAV_PREFIX) ? target.slice(PROJECT_NAV_PREFIX.length) : null;
}
