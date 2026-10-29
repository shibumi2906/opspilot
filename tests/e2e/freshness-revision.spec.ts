import {test,expect} from "../../web/e2e/test";

test("bound mixed intent edit needs a new exact revision decision",async({page})=>{
  await page.getByLabel("What needs attention?").fill("Investigate GreenShop and notify manager");
  await page.getByRole("button",{name:"Start investigation",exact:true}).click();
  const ticket=page.locator('[data-action-key="ticket"]');
  await expect(ticket).toBeVisible();
  const id=new URL(page.url()).searchParams.get("run_id")!;
  const initial=await (await page.request.get(`/api/v2/runs/${id}`)).json();
  const old=initial.actions.find((a:{key:string})=>a.key==="ticket");
  const edit=await page.request.post(`/api/v2/actions/${old.logical_action_id}/revisions`,{data:{expected_version:1,arguments:{...old.arguments,title:"Reviewed replacement needs separate consent"}}});
  expect(edit.status()).toBe(201);
  await expect(ticket).toContainText("Reviewed replacement needs separate consent");
  await expect(ticket.getByTestId("approval-status")).toHaveText("pending");
  const stale=await page.request.post(`/api/v2/runs/${id}/decision`,{data:{action_id:old.action_id,decision:"approve",expected_version:1}});
  expect(stale.status()).toBe(409);
  await ticket.getByRole("button",{name:"Reject action",exact:true}).click();
  await page.locator('[data-action-key="inbox"]').getByRole("button",{name:"Reject action",exact:true}).click();
  await expect(page.getByTestId("plan-node-ticket")).toContainText("rejected");
  const final=await (await page.request.get(`/api/v2/runs/${id}`)).json();
  expect(final.replan_count).toBe(1);
  expect(final.actions.every((a:{result:unknown})=>a.result===null)).toBeTruthy();
});
