# UFAZ Device Issuance

UFAZ IT lends devices to staff, teachers and students. Each loan is recorded on a signed Device Issuance Agreement.

## Language

### The agreement

**Agreement**:
The one-page Device Issuance Agreement for one Receiver and one device, signed by hand.
_Avoid_: Contract, form (as the document)

**Agreement number**:
The identifier printed on an Agreement; unique across everything issued.
_Avoid_: Contract no, ID

**Receiver**:
The staff member, teacher or student who takes the device.
_Avoid_: Borrower, user, employee

**Issuer**:
The IT representative who hands over the device and signs for UFAZ.
_Avoid_: Representative, issued by

**Return terms**:
When the device must come back: a return date, until the end of employment or studies, or upon request.
_Avoid_: Due date

### Producing agreements

**Batch**:
A CSV file with one Receiver per row, turned into one Agreement per row in a single run.
_Avoid_: CSV mode, bulk mode

**Form**:
The on-screen way to fill in and produce Agreements one at a time.
_Avoid_: TUI mode, interactive mode, wizard

**Settings**:
The values that pre-fill or fill in anything left empty: Issuer details and the Agreement number pattern.
_Avoid_: Default config, config, defaults
