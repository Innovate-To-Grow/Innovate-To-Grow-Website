"""CMS seed data for sample-proposals."""

PAGE = {
    "slug": "sample-proposals",
    "route": "/sample-proposals",
    "title": "Sample Project Proposals",
    "page_css_class": "proposals-page",
    "blocks": [
        {
            "block_type": "proposal_cards",
            "sort_order": 0,
            "admin_label": "Sample proposals",
            "data": {
                "heading": "Sample Project Proposals",
                "proposals": [
                    {
                        "type": "Engineering Capstone",
                        "title": "Automated Production Line Optimization",
                        "organization": "Sweep",
                        "background": "Sweep is an IoT Internet of things company that harnesses big data and machine learning to improve operational efficiency in industry. We rely on collecting valuable industrial equipment data through non-invasive sensors technologies to service our industrial/commercial customers. Product development of sensor technologies fuels our growth and innovation is crucial to reducing costs and improving capability.",
                        "problem": "Machine Centers of our production process require that product be moved manually between machine centers. This increases the time it takes to produce product and increases the risk for defects due to manual handling of product.",
                        "objectives": "Optimize a manufacturing production line for small to medium runs of electrical and mechanical manufacturing components. Analyze and provide recommendations for most efficiently timed process from circuit board placement, testing, assembly and logistics. Build, manufacture and test, automation components to limit user interaction. Automate production of mechanical injection molded components, pcb assemblies and final product assembly.",
                    },
                    {
                        "type": "Software Capstone",
                        "title": "Business Process Applications for a Public Agency",
                        "organization": "BART",
                        "background": "The client is the SF Bay Area Rapid Transit (BART). They are in the business of moving people in electrified rail cars, across a collective 122 miles of rail tracks around and in the city of San Francisco. They are a public transportation industry headquartered in Oakland, CA. BART is in the midst of a capital improvement renewal effort to upgrade and replace $3B or more in capital infrastructure. There is a need to provide the highest level of professional project management, and to perform this work most efficiently, and accurately.",
                        "problem": "We are looking to bring the latest business technologies to our processes. Improving the efficiency of the project management process by implementing single data base synching from our current databases. Our systems using the maintenance database, Maximo, support the planning, scheduling, recording, and data collection for entire capital and maintenance teams. We need to gather real time data from these databases and collate the data for notifications. By achieving real time notifications and linking data, decisions, planning, and forecasting will be improved. We are flexible on the type of data and how to integrate data and establishing automated notifications.",
                        "objectives": "We have an opportunity for a student group to generate, collate, and distribute data from our Maximo database. We would like an extraction, population, and integration with the data, real time alerts, and business processes that can provide real time data collection and event forecasting. Final development is a user friendly data output that can be integrated into capital project management reports, capturing real time maintenance and capital work.",
                    },
                    {
                        "type": "Engineering Capstone",
                        "title": "Recovery of Starlite Technology",
                        "organization": "NASA Jet Propulsion Laboratory",
                        "background": "The NASA Jet Propulsion Laboratory (JPL) is a Federally Funded Research and Development Center, located in the Arroyo Seco Mountains in Pasadena, CA. Originating as a laboratory of the California Institute of Technology, JPL has been in the aerospace industry since the 1920s. Dedicated to the unmanned exploration of the solar system, JPL has built interplanetary probes, orbiters, and landers to explore our universe and expand our knowledge.",
                        "problem": "Applications of heat transfer are ubiquitous in spacecraft applications. Examples are protecting the rocket engines from the hot exhaust used for propulsion, keeping sensitive electronics on board thermally insulated from the cold space, as well as protection from solar irradiation. In the 1970s, British hairdresser and amateur chemist Maurice Ward invented Starlite – a material with fantastic thermal properties. He demonstrated that a thin coating of this material could be charred with a blowtorch, but the other side would be cold enough to safely touch it. There was no description of how this material was made, and after Mr. Wards death, there is no knowledge of producing the material. Efforts to reinvent this material were made, but with minimal success.",
                        "objectives": "The recovery of Starlite would be a substantial advancement in space technologies. But with the information available, this material is short of 'unobtaininum', or an imaginary substance. The objective of this project is to research the feasibility, attempt the fabrication, and characterize this material. The material produced should have similar properties, but shall also be properly investigated and understood, such that future generations can produce it as well.",
                    },
                    {
                        "type": "Software Capstone",
                        "title": "Farm Operations Dashboard",
                        "organization": "Bowles Farming Co.",
                        "background": "Bowles Farming Company is a sixth generation family farm out of Los Banos CA. Bowles continuously strives to implement new technology to improve processes and activities around the farm.",
                        "problem": "Agworld is a modern farm management program that allows operations to plan and track jobs and costs associated in one program. We will be using agworld for task assignment and data collection. Agworld has a very robust API which allows programs to extract as much information as needed about jobs in the database. Although a large amount of data is logged in agworld, it is not presented as well as it could be.",
                        "objectives": "A step toward making agworld data presentable is to have a dashboard showing upcoming and completed jobs while highlighting overdue jobs. This data would be presented on TVs or as web platforms for users around the farm to get updated about what is going on and what has happened. This communication tool will help get everyone on the same page about what operations has done and what's coming up.",
                    },
                    {
                        "type": "Engineering Capstone",
                        "title": "Milkweed Harvester",
                        "organization": "Bowles Farming Co.",
                        "background": "Bowles Farming Company is a sixth generation family farm out of Los Banos, CA. Bowles continuously strives to implement new technology to improve processes and activities around the farm.",
                        "problem": "Milkweed is a native species in the California's Central Valley and is a critical element in Monarch habitat, as it provides both forage for adult butterflies and protection for developing larvae. With changes in California land use pressures, milkweed populations have declined, contributing to a correlating decline in monarch populations. Milkweed seed is naturally distributed via pappus (like a dandelion) and when collected, is a mixture of floss and seed. Today, most milkweed is collected by hand, which is a costly and inefficient process. New methods need to be developed for both harvesting and cleaning milkweed seeds in order to efficiently meet the habitat demands of the species.",
                        "objectives": "Milkweed harvesting is the most intensive effort in the production. Milkweed seed is most often collected by hand, and occasionally, via combine. There are significant disadvantages to both. Hand collection of milkweed seed is cost-prohibitive when considering the environmental demands, and combining seed results in the collection of immature materials and can damage the milkweed plants. A successful solution should (1) be mechanized, (2) minimize damage to milkweed plants, and (3) be scalable.",
                    },
                ],
                "footer_html": '<p>Expectations and Submission: please review the <a href="https://docs.google.com/document/d/1HhZ8r7FP9kPeJTSrvy4nBc0A6jBArSd19Y9O9g1xgUc/edit" target="_blank" rel="noopener noreferrer">expectations and terms of the I2G Program</a> for your organization\'s participation, and <a href="https://ucmerced.az1.qualtrics.com/jfe/form/SV_4OA7I03KTLgQcGF?" target="_blank" rel="noopener noreferrer">submit the project with the form</a> or email this filled document to: <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a></p>',
            },
        }
    ],
}
