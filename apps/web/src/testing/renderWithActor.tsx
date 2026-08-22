/** Render a component the way the application renders it.
 *
 * Components that decide what a person may *do* read the session role from
 * `ActorContext`, and `useActor()` throws without a provider — deliberately, so
 * that forgetting the provider in the real app fails loudly instead of silently
 * showing everyone a viewer's interface.
 *
 * A test that renders such a component bare is therefore rendering something
 * the app never renders. This helper supplies the real provider, so the test
 * exercises the real path. With no stored session the provider falls back to
 * the locally stored actor, which is how every existing test behaved before any
 * role gating existed — so wrapping does not change what those tests assert.
 *
 * To test a *specific* role, seed a session first (see `roleGatedActions.test.tsx`);
 * that file drives the same provider from a real stored session.
 */
import type { ReactElement, ReactNode } from "react";
import { render as rtlRender, type RenderOptions, type RenderResult } from "@testing-library/react";
import { ActorProvider } from "../ActorContext";

function Wrapper({ children }: { children: ReactNode }) {
  return <ActorProvider>{children}</ActorProvider>;
}

export function render(ui: ReactElement, options?: Omit<RenderOptions, "wrapper">): RenderResult {
  return rtlRender(ui, { ...options, wrapper: Wrapper });
}
