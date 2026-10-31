/**
 * The client card's Google Drive buttons: "Drive folder" opens the folder in
 * a new tab, "Photos" only when that link is set, "Add folder" (staff only)
 * when there's no folder -- never a broken link. The URL check must match
 * backend/app/libs/drive_links.py.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import "../../test/setup";
import { DriveLinks, driveUrlProblem, isDriveUrl } from "../clients/DriveLinks";

const FOLDER = "https://drive.google.com/drive/folders/1AbC";
const PHOTOS = "https://drive.google.com/drive/folders/9ZyX";

describe("isDriveUrl", () => {
  it.each([
    [FOLDER, true],
    [`  ${FOLDER} `, true],
    ["https://drive.google.com/drive/u/0/folders/abc?usp=sharing", true],
    ["http://drive.google.com/drive/folders/x", false],
    ["https://docs.google.com/document/d/x", false],
    ["https://drive.google.com.evil.com/x", false],
    ["https://user@drive.google.com/drive/folders/x", false],
    ["https://drive.google.com/", false],
    ["javascript:alert(1)", false],
    ["drive.google.com/drive/folders/x", false],
    ["https://drive.google.com/a b", false],
    ["", false],
  ])("%s -> %s", (url, ok) => {
    expect(isDriveUrl(url)).toBe(ok);
  });

  it("explains a bad link, accepts blank (clears it)", () => {
    expect(driveUrlProblem("", "Drive folder")).toBe("");
    expect(driveUrlProblem("https://example.com", "Photos folder")).toMatch(/Photos folder must be/);
  });
});

describe("DriveLinks", () => {
  it("opens the folder and photos in a new tab", () => {
    const html = renderToStaticMarkup(
      <DriveLinks clientId={1} editable links={{ drive_folder_url: FOLDER, drive_photos_url: PHOTOS }} />,
    );
    expect(html).toContain(`href="${FOLDER}"`);
    expect(html).toContain(`href="${PHOTOS}"`);
    expect(html.match(/target="_blank"/g)).toHaveLength(2);
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("Drive folder");
    expect(html).toContain("Photos");
    expect(html).toContain('aria-label="Edit Drive links"');
    expect(html).not.toContain("Add folder");
  });

  it("no Photos button without a photos link", () => {
    const html = renderToStaticMarkup(<DriveLinks clientId={1} editable links={{ drive_folder_url: FOLDER }} />);
    expect(html).toContain("Drive folder");
    expect(html).not.toContain("Photos");
  });

  it("offers Add folder to staff when empty, and nothing to view-only logins", () => {
    const staff = renderToStaticMarkup(<DriveLinks clientId={1} editable links={{}} />);
    expect(staff).toContain("Add folder");
    expect(staff).not.toContain("href=");
    expect(renderToStaticMarkup(<DriveLinks clientId={1} editable={false} links={{}} />)).toBe("");
  });

  it("view-only logins open the links but get no edit button", () => {
    const html = renderToStaticMarkup(
      <DriveLinks clientId={1} editable={false} links={{ drive_folder_url: FOLDER }} />,
    );
    expect(html).toContain(`href="${FOLDER}"`);
    expect(html).not.toContain("Edit Drive links");
  });

  it("never renders a stored link that isn't Drive", () => {
    const html = renderToStaticMarkup(
      <DriveLinks clientId={1} editable links={{ drive_folder_url: "https://evil.com/x" }} />,
    );
    expect(html).not.toContain("evil.com");
    expect(html).toContain("Add folder");
  });
});
