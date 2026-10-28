import {test,expect} from "../../web/e2e/test";

for(const ticketChoice of ["approve","reject"] as const){
  test(`mixed plan: ${ticketChoice} ticket, opposite inbox, concrete comment wave`,async({page})=>{
    await page.getByLabel("What needs attention?").fill("Investigate GreenShop and notify manager and add a ticket comment");
    await page.getByRole("button",{name:"Start investigation",exact:true}).click();
    const ticket=page.locator('[data-action-key="ticket"]');
    const inbox=page.locator('[data-action-key="inbox"]');
    await expect(ticket).toBeVisible();await expect(inbox).toBeVisible();
    await expect(page.locator('[data-action-key="comment"]')).toHaveCount(0);
    await ticket.getByRole("button",{name:ticketChoice==="approve"?"Approve & create ticket":"Reject action",exact:true}).click();
    await expect(ticket.getByTestId("approval-status")).toHaveText(ticketChoice==="approve"?"approved":"rejected");
    const id=new URL(page.url()).searchParams.get("run_id")!;
    const partial=await (await page.request.get(`/api/v2/runs/${id}`)).json();
    expect(partial.status).toBe("waiting_for_approval");
    expect(partial.actions.every((a:{result:unknown})=>a.result===null)).toBeTruthy();
    await inbox.getByRole("button",{name:ticketChoice==="approve"?"Reject action":"Approve & notify recipient",exact:true}).click();
    if(ticketChoice==="approve"){
      const comment=page.locator('[data-action-key="comment"]');
      await expect(comment).toBeVisible();
      await expect(comment.getByTestId("approval-status")).toHaveText("pending");
      const wave=await (await page.request.get(`/api/v2/runs/${id}`)).json();
      expect(wave.plan.wave).toBe(2);
      const root=wave.actions.find((a:{key:string})=>a.key==="ticket");
      const card=wave.actions.find((a:{key:string})=>a.key==="comment");
      expect(card.arguments.ticket_id).toBe(root.result.ticket_id);
      await expect(comment).toContainText(root.result.ticket_id);
      await comment.getByRole("button",{name:"Approve & add comment",exact:true}).click();
    }
    await expect(page.getByRole("region",{name:"Per-action results"})).toBeVisible();
    await expect(page.getByTestId("plan-node-ticket")).toContainText(ticketChoice==="approve"?"verified":"rejected");
    await expect(page.getByTestId("plan-node-inbox")).toContainText(ticketChoice==="approve"?"rejected":"verified");
    await expect(page.getByTestId("plan-node-comment")).toContainText(ticketChoice==="approve"?"verified":"skipped_dependency");
    await expect(page.getByTestId("verification-status")).not.toHaveText("verified");
    const final=await (await page.request.get(`/api/v2/runs/${id}`)).json();
    expect(final.outcome).toBe("actions_partially_verified");
    expect(final.report.effects).toHaveLength(3);
  });
}
