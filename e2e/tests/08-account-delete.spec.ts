import { expect, test } from "@playwright/test";
import {
  acceptInvite,
  createInvite,
  deleteMe,
  endLink,
  inviteToken,
  listLinks,
  provisionUser,
  uniqueEmail,
} from "../helpers/api.js";

// Golden path 8 — account deletion is blocked while care links are active
// (409), and succeeds after the link is ended.

test("DELETE /v1/me blocked by active care link, allowed after end", async () => {
  const patient = await provisionUser("del-pat", "Patient", "E2E Del Patient");
  const caregiverEmail = uniqueEmail("del-cg");
  const caregiver = await provisionUser(
    "del-cg",
    "Caregiver",
    "E2E Del Caregiver",
    caregiverEmail,
  );

  const inviteId = await createInvite(patient.token, caregiverEmail);
  await acceptInvite(caregiver.token, inviteToken(inviteId));

  // Active link → deletion refused.
  const blocked = await deleteMe(patient.token);
  expect(blocked.status).toBe(409);

  // End the link → deletion proceeds.
  const links = await listLinks(patient.token);
  expect(links.length).toBe(1);
  await endLink(patient.token, links[0].linkId);
  const ok = await deleteMe(patient.token);
  expect(ok.status).toBe(204);
});
