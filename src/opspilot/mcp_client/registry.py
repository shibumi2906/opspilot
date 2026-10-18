from typing import NamedTuple

from opspilot.contracts.common import StrictModel
from opspilot.contracts.tools import (
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
    GetTicketArgs,
    IncidentsData,
    IntegrationArgs,
    SearchDocumentationArgs,
    SearchIncidentsArgs,
    ServiceData,
    TicketData,
)


class ToolContract(NamedTuple):
    arguments: type[StrictModel]
    data: type[StrictModel]


READ_TOOLS = {
    "find_customers": ToolContract(FindCustomersArgs, CustomersData),
    "get_customer": ToolContract(GetCustomerArgs, CustomerData),
    "get_service_status": ToolContract(IntegrationArgs, ServiceData),
    "get_integration_events": ToolContract(EventsArgs, EventsData),
    "get_credential_status": ToolContract(IntegrationArgs, CredentialData),
    "search_incidents": ToolContract(SearchIncidentsArgs, IncidentsData),
    "search_documentation": ToolContract(SearchDocumentationArgs, DocumentationData),
    "get_ticket": ToolContract(GetTicketArgs, TicketData),
}

WRITE_TOOLS = {"create_ticket": ToolContract(CreateTicketArgs, CreateTicketData)}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS
