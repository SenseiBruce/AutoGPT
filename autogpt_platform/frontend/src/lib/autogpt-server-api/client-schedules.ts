/** SchedulesApi BackendAPI methods. */

import type {
  GraphID,
  OttoQuery,
  OttoResponse,
  Schedule,
  ScheduleCreatable,
  ScheduleID,
} from "./types";
import { parseScheduleTimestamp } from "./client-helpers";

import type { BackendAPIBase } from "./client-base";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Constructor<T = object> = new (...args: any[]) => T;

export function withSchedulesApi<TBase extends Constructor<BackendAPIBase>>(Base: TBase) {
  return class extends Base {
      /////////// SCHEDULES ////////////
      //////////////////////////////////

      async createGraphExecutionSchedule(
        params: ScheduleCreatable,
      ): Promise<Schedule> {
        return this._request(
          "POST",
          `/graphs/${params.graph_id}/schedules`,
          params,
        ).then(parseScheduleTimestamp);
      }

      async listGraphExecutionSchedules(graphID: GraphID): Promise<Schedule[]> {
        return this._get(`/graphs/${graphID}/schedules`).then((schedules) =>
          schedules.map(parseScheduleTimestamp),
        );
      }

      /** @deprecated only used in legacy `Monitor` */
      async listAllGraphsExecutionSchedules(): Promise<Schedule[]> {
        return this._get(`/schedules`).then((schedules) =>
          schedules.map(parseScheduleTimestamp),
        );
      }

      async deleteGraphExecutionSchedule(
        scheduleID: ScheduleID,
      ): Promise<{ id: ScheduleID }> {
        return this._request("DELETE", `/schedules/${scheduleID}`);
      }

      //////////////////////////////////
      ////////////// OTTO //////////////
      //////////////////////////////////

      async askOtto(query: OttoQuery): Promise<OttoResponse> {
        return this._request("POST", "/otto/ask", query);
      }

      ////////////////////////////////////////
  };
}
