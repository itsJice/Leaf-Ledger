/*
This file is here for exporting a stable API for users apps.

Usage examples:

  // API endpoints can be called via the app apiClient
  // assuming an endpoint definition like @router.get("/example-endpoint")
  import { apiClient } from "app";
  const response = await apiClient.example_endpoint({...})

*/

export { APP_BASE_PATH } from "../constants";

export { default as apiClient } from "../apiclient";
