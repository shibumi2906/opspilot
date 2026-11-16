from typing import NamedTuple

from opspilot.contracts.common import StrictModel
from opspilot.contracts.tools import (
    AddTicketCommentArgs,
    CommentData,
    CommentReceipt,
    CreateJiraCommentArgs,
    CreateJiraIssueArgs,
    CreateTicketArgs,
    CreateTicketData,
    CredentialData,
    CustomerData,
    CustomersData,
    DocumentationData,
    EventsArgs,
    EventsData,
    FindCustomersArgs,
    GetCustomerArgs,
    GetJiraOperationArgs,
    GetNotificationArgs,
    GetTicketArgs,
    GetTicketCommentArgs,
    IncidentsData,
    IntegrationArgs,
    JiraOperationData,
    JiraReceipt,
    NotificationData,
    NotificationReceipt,
    NotifyManagerArgs,
    SearchDocumentationArgs,
    SearchIncidentsArgs,
    ServiceData,
    TicketData,
)


class ToolContract(NamedTuple):
    arguments: type[StrictModel]
    data: type[StrictModel]


READ_TOOLS = {
    "get_jira_operation": ToolContract(GetJiraOperationArgs, JiraOperationData),
    "find_customers": ToolContract(FindCustomersArgs, CustomersData),
    "get_customer": ToolContract(GetCustomerArgs, CustomerData),
    "get_service_status": ToolContract(IntegrationArgs, ServiceData),
    "get_integration_events": ToolContract(EventsArgs, EventsData),
    "get_credential_status": ToolContract(IntegrationArgs, CredentialData),
    "search_incidents": ToolContract(SearchIncidentsArgs, IncidentsData),
    "search_documentation": ToolContract(SearchDocumentationArgs, DocumentationData),
    "get_ticket": ToolContract(GetTicketArgs, TicketData),
    "get_ticket_comment": ToolContract(GetTicketCommentArgs, CommentData),
    "get_notification": ToolContract(GetNotificationArgs, NotificationData),
}

WRITE_TOOLS = {
    "create_jira_issue": ToolContract(CreateJiraIssueArgs, JiraReceipt),
    "create_jira_comment": ToolContract(CreateJiraCommentArgs, JiraReceipt),
    "create_ticket": ToolContract(CreateTicketArgs, CreateTicketData),
    "add_ticket_comment": ToolContract(AddTicketCommentArgs, CommentReceipt),
    "notify_manager": ToolContract(NotifyManagerArgs, NotificationReceipt),
}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS
