# No shared counter for Agreement numbers

The Form also runs in the browser, hosted on Vercel, where the server remembers nothing between requests. We decided not to add a shared store (such as Upstash Redis) that hands out Agreement numbers. Each browser remembers the last number it used, so one Issuer's numbers never repeat, but two Issuers who generate in the same minute can get the same YYMMddhhmm number.

This was already possible with two laptops running `generate`, it is rare, and the number stays editable on the Form. A shared store would add a paid service, more setup and one more thing that can fail, for a small internal tool. So the glossary says an Agreement number *should* be unique, and the Issuer checks it.
