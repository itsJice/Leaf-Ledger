/*
This file is here for exporting a stable API for users apps.

Usage examples:

  // API endpoints can be called via the app apiClient
  // assuming an endpoint definition like @router.get("/example-endpoint")
  import { apiClient, apiTypes } from "app";
  const response: apiTypes.EndpointExampleResponseType = await apiClient.example_endpoint({...})

  // API websocket endpoints are reachable at `${WS_API_URL}/example-websocket-endpoint`
  // assuming an endpoint definition like @router.get("/example-websocket-endpoint")
  import { WS_API_URL } from "app";
  const socket = new WebSocket(`${WS_API_URL}/example-websocket-endpoint`)

  // API HTTP endpoints are also reachable at `${API_URL}/example-endpoint`
  import { API_URL } from "app";

*/

export {
  API_URL,
  APP_BASE_PATH,
  APP_ID,
  Mode,
  WS_API_URL,
  mode,
} from "../constants";

export * from "./auth";
export * from "./analytics";

export { default as apiClient } from "../apiclient";
export * as apiTypes from "../apiclient/data-contracts";
