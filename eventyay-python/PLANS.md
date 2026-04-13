# add front_page text and images

## getting info from old event

- the old event returns the info in these fields 
```json
{
    "data": {
        "type": "event",
        "attributes": {
            "is-demoted": false,
            "stream-loop": false,
            "chat-room-name": "FOSSASIA-Summit-2026-88882f3e",
            "ticket-url": null,
            "privacy": "public",
            "is-sponsors-enabled": true,
            "latitude": 0.0,
            "paypal-email": "office@fossasia.org",
            "location-name": "True Digital Park West, Soi Punnawithi 4, Bang Chak Subdistrict, Phra Khanong District, Bangkok, 10260, Thailand",
            "pending-order-sales": null,
            "large-image-url": "https://api.eventyay.com/static/media/events/3997/large/QzhncEpVOF/f78a0223-78a7-4835-a2e4-451c7571f61d.jpg",
            "completed-order-sales": null,
            "placed-order-sales": null,
            "is-chat-enabled": false,
            "is-sessions-speakers-enabled": true,
            "can-pay-by-invoice": false,
            "longitude": 0.0,
            "is-promoted": true,
            "is-cfs-enabled": true,
            "code-of-conduct": null,
            "is-donation-enabled": false,
            "after-order-message": "",
            "can-pay-by-bank": false,
            "external-event-url": null,
            "is-ticket-form-enabled": true,
            "payment-currency": "THB",
            "is-featured": true,
            "is-stripe-linked": true,
            "is-badges-enabled": false,
            "icon-image-url": "https://api.eventyay.com/static/media/events/3997/icon/a2FINGcySF/f407728f-9207-4d9e-9e2d-30710d47d0db.jpg",
            "xcal-url": "https://api.eventyay.com/static/media/exports/3997/xcal/KzI3Q0RmK1/xcal.xcs",
            "is-document-enabled": false,
            "can-pay-by-omise": false,
            "deleted-at": null,
            "is-map-shown": true,
            "state": "published",
            "cheque-details": null,
            "online": true,
            "is-videoroom-enabled": true,
            "is-oneclick-signup-enabled": false,
            "timezone": "Asia/Bangkok",
            "can-pay-by-paypal": false,
            "can-pay-onsite": false,
            "owner-description": null,
            "pending-order-tickets": null,
            "can-pay-by-cheque": false,
            "is-billing-info-mandatory": false,
            "show-remaining-tickets": false,
            "pentabarf-url": "https://api.eventyay.com/static/media/exports/3997/pentabarf/Y0tpLzcxRm/pentabarf.xml",
            "owner-name": null,
            "is-tax-enabled": false,
            "placed-order-tickets": null,
            "ical-url": "https://api.eventyay.com/static/media/exports/3997/ical/MWU4NUNyRH/event_ical.ics",
            "refund-policy": "At FOSSASIA, we strive to offer an affordable and valuable event experience for all participants. As a non-profit, community-driven event, we carefully allocate resources to ensure a high-quality summit while keeping ticket prices accessible. All ticket sales for the FOSSASIA Summit are final. Once a ticket has been purchased, it is non-refundable and non-transferable. By purchasing a ticket, attendees agree to the terms of this refund policy.",
            "searchable-location-name": null,
            "onsite-details": null,
            "starts-at": "2026-03-08T02:00:00+00:00",
            "can-pay-by-alipay": false,
            "stream-autoplay": false,
            "name": "FOSSASIA Summit 2026",
            "ends-at": "2026-03-10T12:30:00+00:00",
            "description": "<p>FOSSASIA Summit 2026 returns to Bangkok on 8–10 March 2026 at True Digital Park, bringing together <strong>200+ international speakers</strong> across key tracks including <strong>AI &amp; Data, PostgreSQL (PGDay), Cloud &amp; DevOps, Cybersecurity &amp; Privacy, Web &amp; Mobile Development, Operating Systems, and Open Hardware</strong>. Participants will gain practical, production-ready insights into building real-world AI applications, running PostgreSQL at scale, modern DevOps and observability with Kubernetes, and safeguarding security and privacy in the age of AI.</p><p><strong>COMMUNITY DAY - 8 MARCH</strong></p><p>Join the free Community Day on March 8 ahead of the main summit, featuring Open Source 101 and practical tools to help you start or deepen your developer journey.</p><p><strong>FOSSASIA PGDAY - 10 MARCH</strong></p>FOSSASIA PGDay is a co-located event focused on PostgreSQL and its ecosystem, covering performance, HA/DR, backups, security, and operations. A standard FOSSASIA Summit ticket includes PGDay access. Learn more at <a href=\"https://summit.fossasia.org/pgday\" rel=\"nofollow\" target=\"_blank\">https://summit.fossasia.org/pgday</a><p></p><p></p><p><strong>FOSSASIA HACKATHON - 10 MARCH</strong></p><p>Join our one-day hackathon, powered by ExpressVPN to build privacy-first solutions for digital safety for young users. Grand prize: 29,999 THB (~USD 1,000)<br>Learn more: <a href=\"https://next.eventyay.com/fossasia/hackathon2026\" rel=\"nofollow\" target=\"_blank\">https://next.eventyay.com/fossasia/hackathon2026</a></p><p></p>",
            "invoice-details": null,
            "payment-country": "Singapore",
            "document-links": [
                {
                    "link": "",
                    "name": ""
                }
            ],
            "bank-details": null,
            "original-image-url": "https://api.eventyay.com/static/media/temp/images/a70d7d4e-1abc-4a5b-aea0-5969d879d782/elNzUER1c1/046b7f8a-15e9-4b0c-a003-d37289b28083.jpeg",
            "thumbnail-image-url": "https://api.eventyay.com/static/media/events/3997/thumbnail/TlJvV0R5Sl/65aa3ced-6ce0-44e4-bb0b-6db50026f8d3.jpg",
            "identifier": "88882f3e",
            "schedule-published-on": "2026-02-04T20:33:28.469000+00:00",
            "is-announced": false,
            "completed-order-tickets": null,
            "can-pay-by-paytm": false,
            "has-owner-info": false,
            "can-pay-by-stripe": true,
            "created-at": "2025-05-04T17:05:26.160616+00:00",
            "logo-url": "https://api.eventyay.com/static/media/temp/images/5478e748-fd6a-426b-98cc-21934c20ad08/UitOSnRLWF/fd95fa20-971c-4232-8703-1638ba4b292c.png",
            "public-stream-link": ""
        },
        "relationships": {
            "orders": {
                "links": {
                    "self": "/v1/events/3997/relationships/orders",
                    "related": "/v1/events/3997/orders"
                }
            },
            "roles": {
                "links": {
                    "self": "/v1/events/3997/relationships/roles",
                    "related": "/v1/events/3997/users-events-roles"
                }
            },
            "speakers": {
                "links": {
                    "self": "/v1/events/3997/relationships/speakers",
                    "related": "/v1/events/3997/speakers"
                }
            },
            "event-copyright": {
                "links": {
                    "self": "/v1/events/3997/relationships/event-copyright",
                    "related": "/v1/events/3997/event-copyright"
                }
            },
            "session-favourites": {
                "links": {
                    "related": "/v1/events/3997/user-favourite-sessions"
                }
            },
            "role-invites": {
                "links": {
                    "self": "/v1/events/3997/relationships/role-invites",
                    "related": "/v1/events/3997/role-invites"
                }
            },
            "event-topic": {
                "links": {
                    "self": "/v1/events/3997/relationships/event-topic",
                    "related": "/v1/events/3997/event-topic"
                }
            },
            "faqs": {
                "links": {
                    "self": "/v1/events/3997/relationships/faqs",
                    "related": "/v1/events/3997/faqs"
                }
            },
            "social-links": {
                "links": {
                    "self": "/v1/events/3997/relationships/social-links",
                    "related": "/v1/events/3997/social-links"
                }
            },
            "attendees": {
                "links": {
                    "self": "/v1/events/3997/relationships/attendees",
                    "related": "/v1/events/3997/attendees"
                }
            },
            "microlocations": {
                "links": {
                    "self": "/v1/events/3997/relationships/microlocations",
                    "related": "/v1/events/3997/microlocations"
                }
            },
            "order-statistics": {
                "links": {
                    "self": "/v1/events/3997/relationships/order-statistics",
                    "related": "/v1/events/3997/order-statistics"
                }
            },
            "coorganizers": {
                "links": {
                    "self": "/v1/events/3997/relationships/coorganizers",
                    "related": "/v1/users"
                }
            },
            "tax": {
                "links": {
                    "self": "/v1/events/3997/relationships/tax",
                    "related": "/v1/events/3997/tax"
                }
            },
            "registrars": {
                "links": {
                    "self": "/v1/events/3997/relationships/registrars",
                    "related": "/v1/users"
                }
            },
            "general-statistics": {
                "links": {
                    "self": "/v1/events/3997/relationships/general-statistics",
                    "related": "/v1/events/3997/general-statistics"
                }
            },
            "discount-codes": {
                "links": {
                    "self": "/v1/events/3997/relationships/discount-codes",
                    "related": "/v1/events/3997/discount-codes"
                }
            },
            "faq-types": {
                "links": {
                    "self": "/v1/events/3997/relationships/faq-types",
                    "related": "/v1/events/3997/faq-types"
                }
            },
            "feedbacks": {
                "links": {
                    "self": "/v1/events/3997/relationships/feedbacks",
                    "related": "/v1/events/3997/feedbacks"
                }
            },
            "sponsors": {
                "links": {
                    "self": "/v1/events/3997/relationships/sponsors",
                    "related": "/v1/events/3997/sponsors"
                }
            },
            "event-type": {
                "links": {
                    "self": "/v1/events/3997/relationships/event-type",
                    "related": "/v1/events/3997/event-type"
                }
            },
            "stripe-authorization": {
                "links": {
                    "self": "/v1/stripe-authorizations/3997/relationships/event",
                    "related": "/v1/events/3997/stripe-authorization"
                }
            },
            "tracks": {
                "links": {
                    "self": "/v1/events/3997/relationships/tracks",
                    "related": "/v1/events/3997/tracks"
                }
            },
            "moderators": {
                "links": {
                    "self": "/v1/events/3997/relationships/moderators",
                    "related": "/v1/users"
                }
            },
            "owner": {
                "links": {
                    "self": "/v1/events/3997/relationships/owner",
                    "related": "/v1/events/3997/owner"
                }
            },
            "speakers-call": {
                "links": {
                    "self": "/v1/events/3997/relationships/speakers-call",
                    "related": "/v1/events/3997/speakers-call"
                }
            },
            "organizers": {
                "links": {
                    "self": "/v1/events/3997/relationships/organizers",
                    "related": "/v1/users"
                }
            },
            "event-invoices": {
                "links": {
                    "self": "/v1/events/3997/relationships/event-invoices",
                    "related": "/v1/events/3997/event-invoices"
                }
            },
            "track-organizers": {
                "links": {
                    "self": "/v1/events/3997/relationships/track-organizers",
                    "related": "/v1/users"
                }
            },
            "session-types": {
                "links": {
                    "self": "/v1/events/3997/relationships/session-types",
                    "related": "/v1/events/3997/session-types"
                }
            },
            "tickets": {
                "links": {
                    "self": "/v1/events/3997/relationships/tickets",
                    "related": "/v1/events/3997/tickets"
                }
            },
            "badge-forms": {
                "links": {
                    "self": "/v1/events/3997/relationships/badge-forms",
                    "related": "/v1/events/3997/badge-forms"
                }
            },
            "tags": {
                "links": {
                    "self": "/v1/events/3997/relationships/tags",
                    "related": "/v1/events/3997/tags"
                }
            },
            "video-stream": {
                "links": {
                    "self": "/v1/video-streams/3997/relationships/event",
                    "related": "/v1/events/3997/video-stream"
                }
            },
            "station": {
                "links": {
                    "self": "/v1/events/3997/relationships/station",
                    "related": "/v1/events/3997/stations"
                }
            },
            "group": {
                "links": {
                    "self": "/v1/events/3997/relationships/group",
                    "related": "/v1/events/3997/group"
                }
            },
            "custom-forms": {
                "links": {
                    "self": "/v1/events/3997/relationships/custom-forms",
                    "related": "/v1/events/3997/custom-forms"
                }
            },
            "speaker-invites": {
                "links": {
                    "self": "/v1/events/3997/relationships/speaker-invites",
                    "related": "/v1/events/3997/speaker-invites"
                }
            },
            "ticket-tags": {
                "links": {
                    "self": "/v1/events/3997/relationships/ticket-tags",
                    "related": "/v1/events/3997/ticket-tags"
                }
            },
            "access-codes": {
                "links": {
                    "self": "/v1/events/3997/relationships/access-codes",
                    "related": "/v1/events/3997/access-codes"
                }
            },
            "sessions": {
                "links": {
                    "self": "/v1/events/3997/relationships/sessions",
                    "related": "/v1/events/3997/sessions"
                }
            },
            "exhibitors": {
                "links": {
                    "self": "/v1/events/3997/relationships/exhibitors",
                    "related": "/v1/events/3997/exhibitors"
                }
            },
            "event-sub-topic": {
                "links": {
                    "self": "/v1/events/3997/relationships/event-sub-topic",
                    "related": "/v1/events/3997/event-sub-topic"
                }
            }
        },
        "id": "3997",
        "links": {
            "self": "/v1/events/3997"
        }
    },
    "links": {
        "self": "/v1/events/3997"
    },
    "jsonapi": {
        "version": "1.0"
    }
}
```

## sending frontpage text and images

- frontpage_text: public text shown on the presale page - use the `description` field from the old event
- event_logo_image: event logo URL - use the `original-image-url` field from the old event
- logo_image: header/background image URL - use the `logo-url` field from the old event
