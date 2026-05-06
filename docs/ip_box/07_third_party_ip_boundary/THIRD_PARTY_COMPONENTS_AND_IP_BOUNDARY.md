# Third-Party Components and IP Boundary

The qualifying IP under review is the proprietary SAP IS-U Assistant software layer. It is not SAP, not OpenAI, not Qdrant, not client data and not third-party documentation.

| Component | Type | Purpose | Owned by Company? | Licence / Provider | Risk | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| SAP IS-U | Third-party enterprise software | Consulting subject matter | No | SAP | High if confused with owned IP | SAP objects are references only. |
| SAP standard tables/transactions/programs | Third-party domain objects | Technical classification | No | SAP | Medium | Used as metadata, not owned content. |
| Client data | Confidential customer information | Incident context | No | Client | High | Must be isolated and anonymised for advisor packs. |
| OpenAI API | External AI service | Embeddings and responses | No | OpenAI | Medium | Company owns workflow, not model. |
| Qdrant | Vector database | Retrieval index | No | Qdrant/open-source terms | Low | Infrastructure component. |
| Python | Runtime | Application platform | No | PSF | Low | Runtime only. |
| FastAPI/Jinja/Alpine/Tailwind | Framework/UI libraries | Web application | No | OSS licences | Low | Check licence notices if distributed. |
| ReportLab/pypdf/Pillow/pytesseract | Libraries | PDF/OCR/report support | No | OSS licences | Low/Medium | Confirm licences before commercialization. |
| Proprietary company code | Original software | Product logic | Yes, subject to records | Company | Low | Main qualifying asset candidate. |
| Knowledge base structure | Data model/workflow | Reusable knowledge organization | Yes for structure | Company | Medium | Underlying third-party facts remain third-party. |
| Generated documentation | Internal documentation | Evidence and operations | Yes if company-authored | Company | Medium | Must avoid copying third-party content. |
