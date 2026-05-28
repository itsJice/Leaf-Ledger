import { auth } from "app/auth";
import { API_HOST, API_PATH } from "../constants";
import { Apiclient } from "./Apiclient";
import type { RequestParams } from "./http-client";

const constructBaseUrl = (): string => {
  // If running locally, use the origin instead of the API_HOST
  if (window.location.origin.includes("localhost")) {
    return `${window.location.origin}${API_PATH}`;
  }
  return `${API_HOST}${API_PATH}`;
};

type BaseApiParams = Omit<RequestParams, "signal" | "baseUrl" | "cancelToken">;

const constructBaseApiParams = (): BaseApiParams => {
  return {
    credentials: "include",
    secure: true,
  };
};

const constructClient = () => {
  const baseUrl = constructBaseUrl();
  const baseApiParams = constructBaseApiParams();

  return new Apiclient({
    baseUrl,
    baseApiParams,
    customFetch: (url, options) => {
      // Remove /routes/ segment from path
      const normalizedUrl = url.replace(API_PATH + "/routes", API_PATH);
      return fetch(normalizedUrl, options);
    },
    securityWorker: async () => {
      return {
        headers: {
          Authorization: await auth.getAuthHeaderValue(),
        },
      };
    },
  });
};

const apiclient = constructClient();

export default apiclient;
