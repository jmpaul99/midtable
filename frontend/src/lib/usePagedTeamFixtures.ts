"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { errorMessage } from "@/lib/api";
import type { TeamFixture } from "@/lib/types";
import {
  TEAM_FIXTURE_PAGE_SIZE,
  type TeamFixtureSection,
} from "@/lib/teamFixtures";

type ListState = {
  items: TeamFixture[];
  hasMore: boolean;
  loading: boolean;
  loadingMore: boolean;
  error: string;
  offset: number;
};

const emptyList = (): ListState => ({
  items: [],
  hasMore: false,
  loading: true,
  loadingMore: false,
  error: "",
  offset: 0,
});

type FetchPage = (args: {
  section: TeamFixtureSection;
  limit: number;
  offset: number;
}) => Promise<{ items: TeamFixture[]; has_more: boolean; next_offset: number }>;

export function usePagedTeamFixtures({
  section,
  filterKey,
  fetchPage,
  pageSize = TEAM_FIXTURE_PAGE_SIZE,
}: {
  section: TeamFixtureSection;
  /** Change when filters change to reload from offset 0. */
  filterKey: string;
  fetchPage: FetchPage;
  pageSize?: number;
}) {
  const [list, setList] = useState<ListState>(emptyList);
  const fetchGeneration = useRef(0);

  const load = useCallback(
    async (offset: number, append: boolean) => {
      const generation = ++fetchGeneration.current;
      setList((prev) => ({
        ...prev,
        loading: !append && offset === 0,
        loadingMore: append,
        error: "",
      }));
      try {
        const page = await fetchPage({ section, limit: pageSize, offset });
        if (generation !== fetchGeneration.current) return;
        setList((prev) => ({
          items: append ? [...prev.items, ...page.items] : page.items,
          hasMore: page.has_more,
          loading: false,
          loadingMore: false,
          error: "",
          // Prefer SQL cursor; falling back to item count only for older payloads.
          offset: page.next_offset ?? offset + page.items.length,
        }));
      } catch (e) {
        if (generation !== fetchGeneration.current) return;
        setList((prev) => ({
          ...prev,
          loading: false,
          loadingMore: false,
          error: errorMessage(e),
          ...(append ? {} : { items: [], hasMore: false, offset: 0 }),
        }));
      }
    },
    [fetchPage, pageSize, section],
  );

  useEffect(() => {
    setList(emptyList());
    void load(0, false);
    // filterKey forces refetch when filters change
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional filterKey trigger
  }, [filterKey, load]);

  return {
    items: list.items,
    hasMore: list.hasMore,
    loading: list.loading,
    loadingMore: list.loadingMore,
    error: list.error,
    showMore: () => void load(list.offset, true),
  };
}
