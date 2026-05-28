// Placeholder file for apps without the analytics extension (overwritten by PostHog extension if installed)
export const identify = (
  userId: string,
  traits?: {
    email?: string;
    name?: string;
    [key: string]: any;
  },
) => {
  // No-op placeholder
};
