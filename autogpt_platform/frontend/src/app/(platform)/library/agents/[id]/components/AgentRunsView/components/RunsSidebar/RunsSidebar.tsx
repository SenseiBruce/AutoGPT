"use client";

import React from "react";
import {
  TabsLine,
  TabsLineList,
  TabsLineTrigger,
  TabsLineContent,
} from "@/components/molecules/TabsLine/TabsLine";
import { LibraryAgent } from "@/app/api/__generated__/models/libraryAgent";
import { useRunsSidebar } from "./useRunsSidebar";
import { RunListItem } from "./components/RunListItem";
import { ScheduleListItem } from "./components/ScheduleListItem";
import type { GraphExecutionJobInfo } from "@/app/api/__generated__/models/graphExecutionJobInfo";
import { InfiniteList } from "@/components/molecules/InfiniteList/InfiniteList";
import { ErrorCard } from "@/components/molecules/ErrorCard/ErrorCard";
import { Skeleton } from "@/components/__legacy__/ui/skeleton";
import { cn } from "@/lib/utils";
import type { RunStatusGroup } from "./helpers";

interface RunsSidebarProps {
  agent: LibraryAgent;
  selectedRunId?: string;
  onSelectRun: (id: string) => void;
  onCountsChange?: (info: {
    runsCount: number;
    schedulesCount: number;
    loading?: boolean;
  }) => void;
}

export function RunsSidebar({
  agent,
  selectedRunId,
  onSelectRun,
  onCountsChange,
}: RunsSidebarProps) {
  const {
    runs,
    schedules,
    runsCount,
    schedulesCount,
    error,
    loading,
    fetchMoreRuns,
    hasMoreRuns,
    isFetchingMoreRuns,
    tabValue,
    setTabValue,
    statusGroup,
    setStatusGroup,
  } = useRunsSidebar({
    graphId: agent.graph_id,
    onSelectRun,
    onCountsChange,
  });

  if (error) {
    return <ErrorCard responseError={error} />;
  }

  if (loading) {
    return (
      <div className="ml-6 w-[20vw] space-y-4">
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  return (
    <TabsLine
      value={tabValue}
      onValueChange={(v) => {
        const value = v as "runs" | "scheduled";
        setTabValue(value);
        if (value === "runs") {
          if (runs && runs.length) onSelectRun(runs[0].id);
        } else {
          if (schedules && schedules.length)
            onSelectRun(`schedule:${schedules[0].id}`);
        }
      }}
      className="min-w-0 overflow-hidden"
    >
      <TabsLineList>
        <TabsLineTrigger value="runs">
          Runs <span className="ml-3 inline-block">{runsCount}</span>
        </TabsLineTrigger>
        <TabsLineTrigger value="scheduled">
          Scheduled <span className="ml-3 inline-block">{schedulesCount}</span>
        </TabsLineTrigger>
      </TabsLineList>

      <>
        <TabsLineContent value="runs">
          <RunStatusFilterBar
            value={statusGroup}
            onChange={setStatusGroup}
            matchCount={runs.length}
          />
          {runs.length === 0 ? (
            <p className="px-1 py-3 text-sm text-zinc-500">
              No runs match this filter.
            </p>
          ) : (
            <InfiniteList
              items={runs}
              hasMore={!!hasMoreRuns}
              isFetchingMore={isFetchingMoreRuns}
              onEndReached={fetchMoreRuns}
              className="flex flex-nowrap items-center justify-start gap-4 overflow-x-scroll px-1 pb-4 pt-1 lg:flex-col lg:gap-3 lg:overflow-x-hidden"
              itemWrapperClassName="w-auto lg:w-full"
              renderItem={(run) => (
                <div className="w-[15rem] lg:w-full">
                  <RunListItem
                    run={run}
                    title={agent.name}
                    selected={selectedRunId === run.id}
                    onClick={() => onSelectRun && onSelectRun(run.id)}
                  />
                </div>
              )}
            />
          )}
        </TabsLineContent>
        <TabsLineContent value="scheduled">
          <div className="flex flex-nowrap items-center justify-start gap-4 overflow-x-scroll px-1 pb-4 pt-1 lg:flex-col lg:gap-3 lg:overflow-x-hidden">
            {schedules.map((s: GraphExecutionJobInfo) => (
              <div className="w-[15rem] lg:w-full" key={s.id}>
                <ScheduleListItem
                  schedule={s}
                  selected={selectedRunId === `schedule:${s.id}`}
                  onClick={() => onSelectRun(`schedule:${s.id}`)}
                />
              </div>
            ))}
          </div>
        </TabsLineContent>
      </>
    </TabsLine>
  );
}

const STATUS_FILTERS: Array<{ id: RunStatusGroup; label: string }> = [
  { id: "all", label: "All" },
  { id: "failed", label: "Failed" },
  { id: "running", label: "Running" },
  { id: "completed", label: "Done" },
];

function RunStatusFilterBar({
  value,
  onChange,
  matchCount,
}: {
  value: RunStatusGroup;
  onChange: (group: RunStatusGroup) => void;
  matchCount: number;
}) {
  return (
    <div className="mb-2 flex flex-wrap items-center gap-1.5 px-1 pt-1">
      {STATUS_FILTERS.map((filter) => {
        const selected = value === filter.id;
        return (
          <button
            key={filter.id}
            type="button"
            onClick={() => onChange(filter.id)}
            className={cn(
              "rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
              selected
                ? "bg-zinc-800 text-white"
                : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200",
            )}
            aria-pressed={selected}
          >
            {filter.label}
          </button>
        );
      })}
      {value !== "all" ? (
        <span className="ml-1 text-xs text-zinc-500">{matchCount} matching</span>
      ) : null}
    </div>
  );
}
