/** BackendAPI client — composed from domain mixins. */

import { BackendAPIBase } from "./client-base";
import { withGraphsApi } from "./client-graphs";
import { withLibraryApi } from "./client-library";
import { withSchedulesApi } from "./client-schedules";
import { withStoreApi } from "./client-store";
import { withUserApi } from "./client-user";
import { withWebSocketApi } from "./client-websocket";

class BackendAPI extends withWebSocketApi(
  withSchedulesApi(
    withLibraryApi(
      withStoreApi(withGraphsApi(withUserApi(BackendAPIBase))),
    ),
  ),
) {}

export default BackendAPI;
export { BackendAPI };
